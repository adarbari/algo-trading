#!/usr/bin/env bash
# Merge every open PR whose latest commit passed CI. Used by .github/workflows/auto-merge.yml.
#
#   REPO=owner/name scripts/auto_merge.sh [PR_NUMBER ...]   (default: all open PRs)
#   DRY_RUN=1 ...                                           report only, merge nothing
#
# A PR is merged only when all of these hold:
#   - open, not a draft, not from a fork, not labelled "no-automerge"
#   - the latest CI run for its head commit concluded "success"
#   - every check run on that commit completed as success, skipped or neutral
#   - GitHub reports it MERGEABLE (conflicts are left for the author or Dependabot to rebase)
# Each run sweeps every open PR, so a missed or cancelled run is caught by the next one.
set -euo pipefail
: "${REPO:?set REPO=owner/name}"
DRY_RUN=${DRY_RUN:-0}
merged_bases=()

try_merge() {
  local number=$1 pr sha ci bad mergeable base
  pr=$(gh pr view "$number" --repo "$REPO" \
         --json state,isDraft,isCrossRepository,labels,headRefOid,mergeable,baseRefName)
  if [ "$(jq -r .state <<<"$pr")" != "OPEN" ]; then echo "#$number: not open"; return; fi
  if [ "$(jq -r .isCrossRepository <<<"$pr")" = "true" ]; then echo "#$number: from a fork, skipped"; return; fi
  if [ "$(jq -r .isDraft <<<"$pr")" = "true" ]; then echo "#$number: draft, skipped"; return; fi
  if jq -e '.labels | map(.name) | index("no-automerge")' <<<"$pr" >/dev/null; then
    echo "#$number: labelled no-automerge, skipped"; return
  fi
  sha=$(jq -r .headRefOid <<<"$pr")
  ci=$(gh api "repos/$REPO/actions/runs?head_sha=$sha&event=pull_request&per_page=50" \
         --jq '[.workflow_runs[] | select(.name == "CI")] | sort_by(.created_at) | last
               | if . == null then "missing" else (.conclusion // .status) end')
  if [ "$ci" != "success" ]; then echo "#$number: CI on ${sha:0:7} is '$ci', waiting"; return; fi
  bad=$(gh api "repos/$REPO/commits/$sha/check-runs?per_page=100" \
          --jq '[.check_runs[] | select(.status != "completed" or
                 (.conclusion != "success" and .conclusion != "skipped" and .conclusion != "neutral"))
                 | .name] | join(", ")')
  if [ -n "$bad" ]; then echo "#$number: checks not passed: $bad"; return; fi
  # GitHub computes mergeability lazily and resets it whenever the base branch moves, so the
  # first answer is often UNKNOWN. Ask again a few times before giving up until the next sweep.
  mergeable=$(jq -r .mergeable <<<"$pr")
  for _ in 1 2 3 4 5; do
    [ "$mergeable" = "UNKNOWN" ] || break
    sleep "${MERGEABLE_POLL_SECONDS:-3}"
    mergeable=$(gh pr view "$number" --repo "$REPO" --json mergeable --jq .mergeable)
  done
  if [ "$mergeable" != "MERGEABLE" ]; then echo "#$number: mergeable=$mergeable, waiting"; return; fi
  base=$(jq -r .baseRefName <<<"$pr")
  if [ "$DRY_RUN" = "1" ]; then echo "#$number: WOULD MERGE ${sha:0:7} into $base"; return; fi
  if gh pr merge "$number" --repo "$REPO" --squash --delete-branch --match-head-commit "$sha"; then
    echo "#$number: merged into $base"
    merged_bases+=("$base")
  else
    echo "#$number: merge failed, will retry on the next sweep"
  fi
}

if [ $# -gt 0 ]; then
  numbers=("$@")
else
  numbers=()
  while IFS= read -r n; do numbers+=("$n"); done \
    < <(gh pr list --repo "$REPO" --state open --limit 100 --json number --jq '.[].number')
fi
for n in ${numbers[@]+"${numbers[@]}"}; do try_merge "$n"; done

# GITHUB_TOKEN merges do not trigger push workflows: re-test each branch that changed.
if [ ${#merged_bases[@]} -gt 0 ]; then
  for base in $(printf '%s\n' "${merged_bases[@]}" | sort -u); do
    gh workflow run ci.yml --repo "$REPO" --ref "$base"
    echo "started CI on $base"
  done
fi
