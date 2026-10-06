# ADR 0043: Hosting from the owner's Mac behind Tailscale Funnel; the API serves the built web

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
  reload picks them up, no restart).
- One more GET in the shrink-only allow-list, kept by this ADR.
- The token protects the API on the network, not the files on the Mac (ADR 0040).
