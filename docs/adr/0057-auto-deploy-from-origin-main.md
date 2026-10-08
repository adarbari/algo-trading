# ADR 0057: Auto-deploy from origin/main

**Status:** accepted (2026-10-08; owner decision, architect plan 2026-10-08). Amends
[0044](0044-hosting-from-the-owners-mac.md) (decision 4: code never restarts the agent; the
deploy script was a command the owner ran). Runbook: [docs/hosting.md](../hosting.md)
"Auto-deploy".

## Context
Every merged PR left the hosted site behind until the owner ran `scripts/ops/deploy.sh`, and a
web built against a newer schema than the running API broke pages (2026-10-07). The owner wants
the site to follow `origin/main` by itself, without a deploy interrupting an ingest run and
without a bad deploy silently taking the site down.

## Decision
1. **A second launchd agent, `com.algotrade.deploy`**, runs `scripts/ops/deploy.sh --auto` at
   load and every 300 s. Like the API agent (0044) it is written by `algotrade-api schedule
   --agent deploy` and never installed by code. There is one deployer: the same script, whose
   manual form (`deploy.sh`, `--dry-run`) still does everything.
2. **Deploy only what changed.** `var/deploy/last_sha` is the last deployed commit; the cycle
   fetches, and when `origin/main` has not moved exits at once. Otherwise
   `git diff --name-only <last>..<target>` is mapped to actions by `apps/api/algotrade_api/ops/deploy.py`:
   `uv.lock`, `pyproject.toml`, `.python-version` sync the venv and restart; `apps/web/**` and
   the Makefile rebuild the web; `schema.graphql` both rebuilds and restarts; `apps/api/**`,
   `src/**`, `libs/**`, `config/site/**` restart; a plist writer reports a reinstall; everything
   else (ingestion, docs, tests) is merged only.
3. **Bash orchestrates, Python decides and locks.** The script does git, build, swap,
   notification and log; `algotrade-api deploy-plan | deploy-verify` decide the actions and poll
   `/health`, and `algotrade-ingest deploy-hold` (the ingestion app owns the ingest lock; the API
   may not import storage or jobs) holds the locks. The script body is functions only, so bash has
   parsed it before the merge rewrites it.
4. **Never over an ingest.** The merge and every action run under the store's `deploy` lock and
   its `ingest` run lock (`Backend.lock`, `exclusive_run`, no waiting). Either taken: log
   "skipped" and try again in five minutes. A nightly that finds the deploy lock held is rerun by
   its watchdog; a manual ingest exits busy as for any second run.
5. **Atomic web.** The build goes to `var/deploy/web.next` (`make web-build WEB_DIST=...`,
   stamped as always), the previous `assets/` are copied in (hashed names: open tabs keep
   loading them), then `var/web` is renamed to `web.prev` and `web.next` to `var/web` (a
   directory rename: the API resolves the build directory once).
6. **Order and verification.** Merge to the planned sha, sync, build aside, restart and wait
   until the API reports that commit, swap the web, wait until the served web is stamped with it
   and `/health` has no mismatch, then write `last_sha` (temp file and rename).
7. **Stop, tell, never roll back.** A failed sync, build, restart or verify, a dirty or
   diverged checkout, a `last_sha` off `origin/main`, a missing tool, or 12 failed fetches in a
   row write `var/deploy/blocked` with the reason, send one macOS notification and stop until
   the owner runs `deploy.sh --clear` (or a manual deploy succeeds). `last_sha` is left; nothing
   is rolled back. A plist change never blocks: it notifies "reinstall".
8. One log line per acting cycle in `var/logs/deploy.log`.

## Consequences
- The site is at most five minutes behind `origin/main`, restarted only when the change needs it.
- A deploy that cannot finish leaves the site as it was (or half-deployed: the notification
  says so) and does not retry until the owner looks.
- `ALGOTRADE_DEPLOY_API`, `ALGOTRADE_DEPLOY_NOTIFY` and `ALGOTRADE_DEPLOY_AGENTS` exist for the
  tests (stub tools in a temp git repo); the real script is never run against the checkout there.
