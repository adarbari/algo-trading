# Hosting from the owner's Mac (Tailscale Funnel)

How outside users reach the app: [ADR 0044](adr/0044-hosting-from-the-owners-mac.md). One
public HTTPS address, `https://<machine>.<tailnet>.ts.net`, which Tailscale Funnel forwards to
the API on `127.0.0.1:8000`; the API answers its own routes and serves the built web app for
every other path. Sign-in is Supabase ([ADR 0040](adr/0040-identity-and-roles.md),
[configuration.md](configuration.md#environment)). Everything below is an owner action: no
code installs Tailscale, signs in, loads an agent or changes the Supabase project.

```
browser --HTTPS--> Funnel (tailscaled) --> 127.0.0.1:8000 algotrade-api --> /health, /graphql, REST
                                                                       \-> any other path: var/web (the build)
```

## 1. Build the web app

```bash
make web-build      # -> var/web (VITE_API_BASE_URL empty: API calls go to the same origin)
```

It reads `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` from `apps/web/.env.local`. **Redo it
after every web change** (and after pulling one): the API serves the files as built, and a
reload of the page picks up a new build of web-only changes without restarting the API (during the few seconds
of a build the page may fail to load, and a tab left open from before needs a reload). It writes `var/web`, not
`apps/web/dist`, because `make check` rebuilds `dist` for the development setup (API under
`/api`).

It also stamps the build (`var/web/build.json`: the commit and the GraphQL schema hash) and
asks the running API whether it matches. **A running API keeps the schema and code it started
with**: a build against a newer schema (a pull with API changes) serves queries the old process
cannot answer (2026-10-07: every Builder row empty). Then `make web-build` prints a
`WARNING: the API ... is out of step` with the restart command; run it (section 3).

## 2. Settings in `.env`

```bash
ALGOTRADE_AUTH=supabase                            # never off when hosted (below)
SUPABASE_URL=https://<project-ref>.supabase.co
ALGOTRADE_WEB_DIST=var/web                         # relative to the checkout, or absolute
```

`ALGOTRADE_CORS_ORIGINS` is not needed: the web and the API share one origin. `make doctor`
checks that `ALGOTRADE_WEB_DIST` holds a build and that the installed agent runs this checkout.

## 3. Keep the API running (launchd)

```bash
.venv/bin/algotrade-api schedule   # writes var/com.algotrade.api.plist; prints the install commands
```

Run the `install` commands it prints (`launchctl load ~/Library/LaunchAgents/com.algotrade.api.plist`
after copying it there). The agent starts the API at login and restarts it whenever it exits;
it reads this checkout's `.env` as the nightly does; logs are `var/logs/api.log` and
`var/logs/api.err.log`. After a change to `.env`, `config/site/users.toml` or an
`identity.toml` (read at startup), or after pulling API code, restart it. After a change to the code, `scripts/ops/deploy.sh`
(or the auto-deploy agent below) does it all (main checkout on `main` and clean: `git pull --ff-only`, `make web-build`,
restart, health; `--dry-run` prints the plan). After the restart the API's commit is verified, after the web swap only the served web's, so a web-only deploy leaves the API at its older commit without blocking. After only a config change:

```bash
launchctl kickstart -k gui/$(id -u)/com.algotrade.api
curl -s http://127.0.0.1:8000/health
```

### Is the running API the checked-out code?

`curl -s http://127.0.0.1:8000/health` has a `build` object: the API's stamp (`api`: commit,
schema hash, start time), the served web's (`web`, from `var/web/build.json`), the checkout's
(`checkout`, read now), `stale` and `mismatches`, each with its fix. `make status` prints
`API build: OUT OF STEP` and `make doctor` warns with the same lines. The fixes:

| Mismatch | Fix |
|---|---|
| the web was built against another schema, after the API started | restart: `launchctl kickstart -k gui/$(id -u)/com.algotrade.api` |
| the web was built against another schema, before the API started | `make web-build` |
| the served web has no `build.json` (built outside `make web-build`) | `make web-build` |
| the checkout's schema or commit moved since the API started (a pull) | restart (or `scripts/ops/deploy.sh`) |

The checks only print; nothing restarts the agent for you.

This machine's own site values (the LLM provider, `enabled = true`) live in the git-ignored
`config/site/llm.local.toml`, merged over the committed `llm.toml`
([configuration.md](configuration.md)): the main checkout stays clean and `deploy.sh` runs.

The agent binds `127.0.0.1` only; Funnel is the one way in from outside. Without the agent,
`.venv/bin/algotrade-api` in a terminal serves the same.

### Auto-deploy (launchd, ADR 0057)

The fourth agent, `com.algotrade.deploy`, runs `scripts/ops/deploy.sh --auto` at load and every
5 minutes: it fetches `origin/main` and, when it moved, deploys only what the changed files need
(dependencies: `uv sync` + restart; `apps/web`, Makefile: web build; `schema.graphql`: both;
`apps/api`, `src`, `libs`, `config/site`: restart; ingestion, docs, tests: merge only). Nothing
moved: it exits at once and logs nothing. Install it (written, never installed by code; it
needs `uv`, `npm`, `node`, `git` on the PATH it is written with):

```bash
.venv/bin/algotrade-api schedule --agent deploy   # writes var/com.algotrade.deploy.plist; prints the commands
mkdir -p var/logs
cp var/com.algotrade.deploy.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.algotrade.deploy.plist
```

- **Log:** `var/logs/deploy.log`, one line per acting cycle (`deployed <sha> (restart web)`,
  `skipped: ingest/deploy running`, `BLOCKED: <reason>`). State: `var/deploy/` (`last_sha`, the
  web build in `web.next` / `web.prev`).
- **Blocked:** a failed sync, web build, restart or health check, a main checkout that is dirty,
  off `main` or diverged from `origin/main`, a missing tool, or 12 failed fetches in a row write
  `var/deploy/blocked`, show one macOS notification and stop. Nothing is rolled back; the site
  stays as the failure left it. Fix the cause, then `scripts/ops/deploy.sh --clear` (prints the
  reason and lets the agent run again); a manual `scripts/ops/deploy.sh` that succeeds clears it too.
- **Ingest:** a deploy takes the `deploy` lock, and the ingest run lock too when the change
  touches anything a running ingest loads (anything but web, API, docs, tests, `.claude`,
  `.github`, root `*.md`; a dependency change always does), without waiting, so
  it never runs over an ingest it could disturb (the cycle logs "skipped" and retries in 5
  minutes); a web-only deploy goes ahead during a backfill. While it holds them, a nightly that finds the lock busy is rerun by its watchdog, and a manual
  `algotrade-ingest` exits busy like any second run.
- **Plists:** when a launchd plist writer changed, the cycle regenerates the agents into
  `var/deploy/plists/`, compares them with `~/Library/LaunchAgents/` and notifies
  "reinstall"; it never installs or blocks. Reinstall with the commands each `schedule` prints.
- The manual `scripts/ops/deploy.sh` (and `--dry-run`) still does everything: sync, web, restart.

### The monthly Tiingo history fill (launchd)

The third agent runs `algotrade-ingest bars-history --fill 450 --wait` on the 2nd of each month
at 19:00 local time: the next names without 2018 daily bars (optionable first, by IV30 then dollar
volume), within Tiingo's free limit of 500 distinct tickers a month (`[tiingo]
monthly_symbol_budget = 450` in `config/site/sources.toml`), until the optionable universe is
covered. `algotrade-ingest schedule` writes it next to the nightly's; it is written, never
installed by code. Install it (and replace an installed copy) with:

```bash
.venv/bin/algotrade-ingest schedule   # also writes var/com.algotrade.bars-history-monthly.plist
mkdir -p var/logs
cp var/com.algotrade.bars-history-monthly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.algotrade.bars-history-monthly.plist
```

Logs are `var/logs/bars-history-monthly.log` and `.err.log`. It starts after the 15:00 nightly because 450 names at 72 s hold the ingest lock about 9 hours
(it ends about 04:00); `--wait` queues it behind a running
ingest; a month the Mac is off at that time is skipped (the next run covers the same names).
README "Long runs" says how to check a run.

## 4. Tailscale and Funnel

Commands from Tailscale's docs ([Funnel](https://tailscale.com/kb/1223/funnel),
[`tailscale funnel`](https://tailscale.com/kb/1311/tailscale-funnel),
[macOS variants](https://tailscale.com/kb/1065/macos-variants), checked 2026-10-05).

1. **Install a variant that supports Funnel.** Tailscale's variant table lists no Funnel
   support for the **Mac App Store** app, so use the Standalone app (download from
   tailscale.com; Settings -> CLI integration installs `/usr/local/bin/tailscale`) or the
   open-source `tailscaled` from Homebrew, which also runs before login:

   ```bash
   brew install --formula tailscale
   sudo brew services start tailscale
   sudo tailscale up            # sign in in the browser it opens
   ```
2. **Admin console** (login.tailscale.com): DNS -> enable **MagicDNS** and **HTTPS
   Certificates**; Access controls -> add the Funnel node attribute to the tailnet policy file:

   ```json
   "nodeAttrs": [
     {
       "target": ["autogroup:member"],
       "attr":   ["funnel"],
     },
   ],
   ```
3. **Turn Funnel on**, in the background so it survives reboots and `tailscale down` / `up`:

   ```bash
   tailscale funnel --bg localhost:8000
   ```

   It prints the public address (`https://<machine>.<tailnet>.ts.net`). Funnel listens on 443
   (also allowed: 8443, 10000).
4. **Check it**: `tailscale funnel status` (or `tailscale serve status`); from a phone off the
   Wi-Fi, open the address: the sign-in page loads, `/health` answers JSON.
5. **Turn it off**: `tailscale funnel reset` (removes this machine's Funnel / Serve config).

With the Homebrew `tailscaled`, prefix these commands with `sudo` (as its `tailscale up`).

## 5. Supabase

Authentication -> URL Configuration: **Site URL** `https://<machine>.<tailnet>.ts.net`; add the
same address to **Redirect URLs**, and keep `http://localhost:5173` there for development. The
rest of the project checklist is in [configuration.md](configuration.md#environment) (sign-ups
off, confirm email on, anonymous off).

## 6. Onboarding a user

1. Supabase: Authentication -> Users -> **Add user** -> create with their email and a password
   (sign-ups are off, so this is the only way in; tell them the password out of band).
2. Declare them in `config/site/users.toml` (a PR: the file is public, no emails in it):

   ```toml
   [[user]]
   id = "alice"
   role = "trader"     # or "admin"
   name = "Alice"
   ```
3. Their git-ignored `config/users/alice/identity.toml`: `email = "alice@example.com"`, and after
   their first sign-in optionally `subject = "<UID>"` from Authentication -> Users.
4. Restart the API (`scripts/ops/deploy.sh`, or `launchctl kickstart -k gui/$(id -u)/com.algotrade.api` for config only).

`Too many open files` / `socket.accept() out of system resource` in `api.err.log`: launchd
gives an agent 256 descriptors and every open connection takes one. The agent's plist sets
`NumberOfFiles` and the CLI raises its own soft limit when it starts, so a restart is enough;
past `MAX_CONNECTIONS` (`ops/schedule.py`) connections are answered 503. Slow answers with
few connections open usually mean the Mac is swapping (`sysctl vm.swapusage`).

## The Mac

The site is up only while the Mac is awake, online and logged in (the API agent is a user
launchd agent, like the nightly's). Keep it on power with sleep off on power
(`sudo pmset -c sleep 0`, or System Settings -> Battery -> Options: prevent automatic sleeping
when the display is off), and with the lid open or an external display (a closed lid on
battery sleeps). `pmset -g` shows the current settings. The nightly needs the same (README,
"Scheduling the nightly").

## Safety

- **Never host with `ALGOTRADE_AUTH=off`.** Funnel hands requests to the API on loopback, so
  off mode refuses any request carrying `X-Forwarded-For`, `Forwarded` or
  `Tailscale-Funnel-Request` (Tailscale's proxy sets the first and, for Funnel, the last): every
  API call from outside is 401, but the point is not to rely on it. `algotrade-api schedule`
  warns when `.env` says off.
- The page itself (`var/web`) is public: it holds no data. Every API call carries a Supabase
  token (401 without, 403 for an email no `identity.toml` names).
- The token protects the API, not the files on the Mac (ADR 0040).
