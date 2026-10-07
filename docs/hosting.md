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
reload of the page picks up a new build without restarting the API (during the few seconds
of a build the page may fail to load, and a tab left open from before needs a reload). It writes `var/web`, not
`apps/web/dist`, because `make check` rebuilds `dist` for the development setup (API under
`/api`).

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
`identity.toml` (read at startup), or after pulling API code, restart it:

```bash
launchctl kickstart -k gui/$(id -u)/com.algotrade.api
curl -s http://127.0.0.1:8000/health
```

The agent binds `127.0.0.1` only; Funnel is the one way in from outside. Without the agent,
`.venv/bin/algotrade-api` in a terminal serves the same.

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
4. Restart the API (`launchctl kickstart -k gui/$(id -u)/com.algotrade.api`).

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
