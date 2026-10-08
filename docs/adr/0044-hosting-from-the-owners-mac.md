# ADR 0044: Hosting from the owner's Mac behind Tailscale Funnel; the API serves the built web

**Status:** accepted (2026-10-05; owner decision on the host, roadmap H1). Amends
[0037](0037-domain-read-model-served-by-graphql.md) decision 4 (the "files" kept by REST
include the built web app, one more `keep` entry in the GET allow-list) and extends
[0040](0040-identity-and-roles.md) (the hosted API and web that ADR anticipates). Runbook:
[docs/hosting.md](../hosting.md).

## Context
Outside users need the app within the week (ADR 0040). The store, the nightly and the IB
Gateway live on the owner's MacBook, so the owner hosts from it rather than moving the data. The
Mac has no public address or domain. Tailscale Funnel gives a machine a public HTTPS name
(`https://<machine>.<tailnet>.ts.net`) and forwards to a local port; Tailscale Serve can also
serve a directory and proxy a path prefix. Two ways to put the web and the API behind it:
(a) the API serves the built web on its own origin, or (b) Tailscale Serve serves the build and
proxies `/api` to the API.

## Decision
1. **One origin: the API serves the built web** (a). `ALGOTRADE_WEB_DIST` (read only by
   `algotrade.config.env`) names the Vite build; set, `create_app` mounts `GET /{path}` **last**
   (`algotrade_api/web.py`): a file of the build, else `index.html` (the browser router owns
   deep links), a missing `assets/` file is 404, nothing resolves outside the build directory.
   Unset (tests, development), the API serves no files. Every API route keeps precedence; the
   route is public (the bundle is the same for everyone and holds no data; every API call still
   carries a token). The web is built for the same origin (`VITE_API_BASE_URL=` empty: the API's
   routes at the root), so there is no CORS and nothing depends on how Tailscale rewrites paths.
2. **The route is in the OpenAPI document and the allow-list** (`keep = true`, kind "files"):
   the allow-list test builds the app with a web build so it sees every route the API can serve.
3. **Tailscale Funnel forwards port 443 to `127.0.0.1:8000`**, which the API binds through a
   launchd agent (`algotrade-api schedule`: written, never installed; `RunAtLoad`, `KeepAlive`,
   the checkout's `.env` as the nightly reads it). Hosted, the API runs `ALGOTRADE_AUTH=supabase`.
   `ALGOTRADE_AUTH=off` still refuses what a tunnel forwards: Tailscale's proxy adds
   `X-Forwarded-For` and, for Funnel, `Tailscale-Funnel-Request`, both refused with 401.
4. **Owner actions stay owner actions**: installing Tailscale, signing in, the Funnel policy,
   loading the agent and the Supabase URLs are steps in the runbook, never run by code.

## Consequences
- The site is up only while the Mac is awake and online (the nightly already needs that);
  moving to a server later changes the host, not the app: the same build and settings.
- A web change is live only after `make web-build` (the API serves the files as built; a
  reload picks them up). A change to the API's schema or code also needs a restart of the
  agent: see the amendment below.
- One more GET in the shrink-only allow-list, kept by this ADR.
- The token protects the API on the network, not the files on the Mac (ADR 0040).

## Amendment 2026-10-07: build identity

**Incident.** The agent started at 12:05; GD4a (#279) added `FieldGuide.summary` to the schema
and `make web-build` rebuilt `var/web` at 17:55. The process kept the schema it started with
while serving the new files from disk, every catalogue query failed ("Cannot query field
'summary'") and the Builder showed "Choose a feature…" on every row until the agent was
restarted. The Consequence "no restart" held for web-only changes, not for a web built against
a new API.

**Decision.** The running API knows which build it is and says when it is out of step
(`apps/api/algotrade_api/ops/build.py`, responsibility `build-identity`):
1. `create_app` takes the API's stamp once: the commit of the checkout its code runs from and
   a 12-character hash of its live GraphQL SDL (the same text as `apps/api/schema.graphql`,
   so the same hash).
2. `make web-build` stamps the build: `algotrade-api stamp-web var/web` writes
   `var/web/build.json` (commit, hash of the committed schema the codegen read, build time).
3. `GET /health` adds `build`: the API's, the served web's and the checkout's stamps (the last
   two read on each request), `stale` and `mismatches`, each naming its fix: a web built against
   another schema (restart the agent when the web is newer, else rebuild), a served web without
   a stamp (built outside `make web-build`), a checkout whose schema or commit moved since the
   start (restart). `status` stays `ok`: the API is up; staleness is not downtime.
4. `make web-build`, `make status` and `make doctor` ask the running API's `/health` and print
   the mismatches with `launchctl kickstart -k gui/<uid>/com.algotrade.api`. Code never
   restarts the agent (decision 4): `scripts/ops/deploy.sh` remains the one-command update.
5. The GET of `/health` from `ops/build.py` is our own API on loopback, not a vendor: it is
   `allowed` under `vendor-http` in `architecture/ownership.toml` for that reason.
