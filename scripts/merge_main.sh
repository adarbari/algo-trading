#!/usr/bin/env bash
# Merge origin/main into this branch, resolving the conflicts that are only generated files.
#
#   scripts/merge_main.sh [--dry-run]
#
# Fetches origin/main and merges it. When the merge conflicts ONLY in generated files, takes
# main's version of each and regenerates it, commits the merge, then reruns the gate those files
# belong to. Any other conflicting file: the merge is aborted and the files are listed (nothing
# is changed). --dry-run prints the plan and the generated-file policy, and changes nothing.
#
#   apps/api/openapi.json                         scripts/export_openapi.py
#   apps/api/schema.graphql                       scripts/export_graphql_schema.py
#   apps/web/src/shared/api/generated/*           npm run api:generate        (apps/web)
#   apps/web/design-system/COMPONENTS.md          npm run components:md       (apps/web)
#   apps/web/design-system/tokens/tokens.css      npm run tokens              (apps/web)
#   docs/data/features.md, docs/data/field-guide.md, docs/data/field-guide/**   make features-doc
#   *.png (screenshots)                           main's; rerun `make web-visual` afterwards
#   apps/web/perf-budgets.json, benchmarks/api_latency_views.captured.json   merged by scripts/ops/merge_budgets.py
#   benchmarks/api_latency_views.json            merged, then `make api-latency-views`
#   docs/perf/view-coverage.md                   no longer tracked (var/perf/, 2026-11-02): deleted
#
# Gates after the commit: `npm run generated:check` when a web file was regenerated, and a clean
# `git diff` of docs/data after `make features-doc`. MERGE_MAIN_NO_REGEN=1 skips running the
# generators and gates (tests); PY overrides the Python (default .venv/bin/python).
set -euo pipefail

dry=0
case "${1:-}" in
  --dry-run) dry=1 ;;
  "") ;;
  -h | --help) sed -n '2,23p' "$0"; exit 0 ;;
  *) echo "usage: scripts/merge_main.sh [--dry-run]" >&2; exit 2 ;;
esac

root=$(git rev-parse --show-toplevel)
cd "$root"
PY=${PY:-.venv/bin/python}
noregen=${MERGE_MAIN_NO_REGEN:-0}

# kind of a conflicting path: openapi graphql webgen components tokens docs png, or empty
kind_of() {
  case "$1" in
    apps/api/openapi.json) echo openapi ;;
    apps/api/schema.graphql) echo graphql ;;
    apps/web/src/shared/api/generated/*) echo webgen ;;
    apps/web/design-system/COMPONENTS.md) echo components ;;
    apps/web/design-system/tokens/tokens.css) echo tokens ;;
    docs/data/features.md | docs/data/field-guide.md | docs/data/field-guide/*) echo docs ;;
    apps/web/perf-budgets.json) echo budgets ;;
    benchmarks/api_latency_views.captured.json) echo captured ;;
    benchmarks/api_latency_views.json) echo latency ;;
    docs/perf/view-coverage.md) echo untracked ;;
    *.png) echo png ;;
    *) echo "" ;;
  esac
}

step() { echo "+ $*"; if [ "$noregen" = 1 ]; then echo "  (skipped: MERGE_MAIN_NO_REGEN=1)"; else "$@"; fi; }
webstep() { echo "+ (cd apps/web && $*)"; if [ "$noregen" = 1 ]; then echo "  (skipped: MERGE_MAIN_NO_REGEN=1)"; else (cd apps/web && "$@"); fi; }

if [ "$dry" = 1 ]; then
  echo "[dry-run] git fetch origin main"
  echo "[dry-run] git merge --no-edit origin/main"
  echo "[dry-run] on conflicts only in generated files: take main's, regenerate, commit, run the gates:"
  sed -n '11,20p' "$0" | sed 's/^# /[dry-run]   /'
  echo "[dry-run] any other conflict: abort the merge and list the files"
  exit 0
fi

[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "refusing: uncommitted changes" >&2; exit 1; }
[ ! -f scripts/ops/install_merge_drivers.sh ] || bash scripts/ops/install_merge_drivers.sh >/dev/null  # the drivers of .gitattributes (perf budgets, latency views)
git fetch -q origin main

# the static view list follows the merged code: regenerate and commit when it differs
regen_latency() {
  step make api-latency-views
  git add benchmarks/api_latency_views.json
  git diff --cached --quiet || { git commit -q -m "Regenerate the API latency view list after merging main"; echo "latency views regenerated"; }
}

if git merge --no-edit origin/main; then
  # the driver merged the shared files without a conflict: the view list may still be stale
  if ! git diff --quiet "$(git merge-base ORIG_HEAD origin/main)" origin/main -- benchmarks/api_latency_views.json; then
    regen_latency
  else
    echo "merged cleanly: nothing to regenerate"
  fi
  exit 0
fi

conflicts=$(git diff --name-only --diff-filter=U)
others=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  [ -n "$(kind_of "$f")" ] || others="$others$f"$'\n'
done <<<"$conflicts"
if [ -n "$others" ]; then
  git merge --abort
  echo "conflicts outside the generated files; merge aborted, resolve these by hand:" >&2
  printf '%s' "$others" | sed 's/^/  /' >&2
  exit 1
fi

kinds=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  k=$(kind_of "$f")
  case "$k" in
    untracked) git rm -q -f -- "$f" ;; # main stopped tracking it: the deletion wins
    budgets | captured | latency)
      # the driver did not run (not installed, or unparsable JSON): rerun it on the three stages
      d=$(mktemp -d)
      git show ":1:$f" >"$d/base" 2>/dev/null || echo '{}' >"$d/base"
      git show ":2:$f" >"$d/ours"
      git show ":3:$f" >"$d/theirs"
      driver=views; [ "$k" = budgets ] && driver=budgets
      if python3 scripts/ops/merge_budgets.py "$driver" "$d/base" "$d/ours" "$d/theirs"; then
        cp "$d/ours" "$f"; git add -- "$f"
      else
        rm -rf "$d"; git merge --abort
        echo "$f does not parse as JSON; merge aborted, resolve it by hand" >&2; exit 1
      fi
      rm -rf "$d" ;;
    *)
      git checkout --theirs -- "$f" 2>/dev/null || git rm -q -- "$f"
      [ -e "$f" ] && git add -- "$f" ;;
  esac
  kinds="$kinds $k"
done <<<"$conflicts"
has() { case " $kinds " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

web=0
has openapi && { step "$PY" scripts/export_openapi.py; git add apps/api/openapi.json; web=1; }
has graphql && { step "$PY" scripts/export_graphql_schema.py; git add apps/api/schema.graphql; web=1; }
has webgen && { webstep npm run api:generate; web=1; }
has components && { webstep npm run components:md; web=1; }
has tokens && { webstep npm run tokens; web=1; }
has docs && { step make features-doc; git add docs/data; }
has latency && { step make api-latency-views; git add benchmarks/api_latency_views.json; }
git add -u
git commit -q --no-edit
echo "merge committed"

if [ "$web" = 1 ]; then webstep npm run generated:check; fi
if has docs && [ "$noregen" != 1 ]; then
  git diff --exit-code -- docs/data || { echo "docs/data differs after make features-doc" >&2; exit 1; }
fi
has png && echo "screenshots: took main's PNGs; run \`make web-visual\` (or npm run visual:update) and commit the diffs"
exit 0
