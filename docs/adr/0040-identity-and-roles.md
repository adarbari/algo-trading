# ADR 0040: Users are declared in a site registry with a role; Supabase Auth authenticates them behind one Authenticator seam

**Status:** accepted (2026-10-05; owner decision; implementation: roadmap ID1-ID4), amended 2026-10-08 (the web uses `@supabase/auth-js`, not `supabase-js`; decision 3 and Consequences), amended 2026-10-05: the owner wants outside users on a hosted API within a week, so Supabase Auth replaces the local login (decision 3) and the seam of decision 5 is its home. Closes the
open decision "User identity scheme" (phase 4) and extends [0015](0015-configs-selections-users.md)
(users as labels), [0024](0024-api.md), [0029](0029-rule-screener.md) (`?user=` on writes),
[0025](0025-frontend-architecture.md) (the role-gating seam `guard.ts`) and
[0037](0037-domain-read-model-served-by-graphql.md) (what stays REST).

## Context
Users exist only as labels: `ALGOTRADE_USER` picks the one user the API serves, a write names
any user with `?user=`, and every workspace is open (`canEnter` returns true). Configs are
already per user on disk (`config/users/<id>/`, ADR 0015) and every service is user-scoped
through `UserContext`, so the missing pieces are: who exists, what they may do, and how the
API knows who is calling. The app ran on one machine for a handful of people. On 2026-10-05 the owner decided to open it
to people outside that machine within a week, so the API will be hosted and reachable from the
internet: password storage, reset flows and session handling are then liabilities we should
not own, and a hosted identity provider stops being over-engineering.

## Decision
1. **A site registry of users with a role.** `config/site/users.toml` (`[[user]]` with `id`,
   `role`, `name`) typed by the one settings loader into `UsersSettings`
   (`config/site/users.py`). Roles are `admin` (TRADER and ADMIN workspaces, the ops reads,
   waivers, writes for any user) and `trader` (TRADER only, writes for themselves). Without
   the file the install is single-user: `local` and `site` are admins, so today's behaviour is
   unchanged. At least one admin must exist; an unknown id is refused everywhere.
2. **Configs belong to the registry's users.** A user's configs stay in `config/users/<id>/`;
   `services/authoring` writes only for a declared user, and the `?user=` query parameter is
   replaced by the authenticated user (an admin may still name another user: ID4 made it the `X-Act-For` header on writes and
   the body's `user` on the preview POSTs; the Admin GraphQL fields are `AdminOnly`).
3. **Supabase Auth authenticates users (amended 2026-10-05; replaces the local login).** The
   web signs in through `@supabase/auth-js` (the auth client `supabase-js` wraps, pinned exactly; email and password first; social providers are Supabase
   configuration, not code) inside `src/shared/api`, the one HTTP layer, and sends the Supabase
   access token as `Authorization: Bearer` on every REST and GraphQL request. The API verifies
   the token offline: the project's JWKS (`SUPABASE_URL`, fetched once at startup, cached,
   refreshed on an unknown `kid`) or the legacy `SUPABASE_JWT_SECRET` (HS256), never a call per
   request. The token's email maps to a registry user; a valid
   token with no registry match is 403, no token is 401. The email is personal data and the
   repo is public, so it is not in `users.toml`: each user's lives in their git-ignored
   `config/users/<id>/identity.toml` (`email = "..."`, amended 2026-10-05 in ID2). Because an
   email alone identifies a user, the Supabase project must have sign-ups off (users are
   invited), email confirmation on and anonymous sign-ins off; `identity.toml` may also pin
   `subject` (the Supabase user id), and then a token whose `sub` differs is 403. No `/auth/*` REST endpoints and no
   password material in the repo. Dev shortcut: `ALGOTRADE_AUTH=off` serves `ALGOTRADE_USER`
   without a token, and the API refuses to start that way when bound to a non-loopback address.
4. **The web learns who is calling from one field.** `Query.viewer { id name role workspaces }`
   (a page read: GraphQL, not REST). `guard.ts` stays the one role-gating seam and reads it;
   a refused workspace redirects to the default; a 401 shows the login page (a design-system
   `LoginForm` component first, then the page). Ops fields and the ADMIN workspace require
   `admin`; the server enforces it, the guard only hides.
5. **The authenticator is one seam.** Exactly one module resolves the caller from a request
   (`apps/api/algotrade_api/auth/`, an `Authenticator` protocol: request in, registry user out
   or 401 / 403); REST deps and the GraphQL context call it and nothing else inspects headers.
   Roles always come from the registry, never from the provider. Supabase is the first
   implementation; another issuer (or a local login for an offline install) is a second
   implementation plus an amendment here; the registry, the services and the guard do not change.
6. **Not now:** social providers (Supabase configuration, when asked), API tokens for scripts (the CLIs keep `ALGOTRADE_USER` on the
   machine that holds the data), per-user data visibility (IB-B stays its own item).

## Consequences
- One new site settings file and one new module; `UserContext` gains nothing until ID3 (the
  resolved user and role become fields on it then).
- No new REST route at all: sign-in is the provider's, the allow-list does not grow. `?user=`
  on writes retires in ID4 (the web client regenerates). The API gains `PyJWT` (its own
  pyproject), the web `@supabase/auth-js` (amended 2026-10-08, was `@supabase/supabase-js`: the same auth code without the database, realtime and storage clients, 54 kB less on every page and a smaller attack surface; the Supabase URL must be https, plain http only for localhost; the session key stays `sb-<project ref>-auth-token`, so sessions survive; ESLint bans `@supabase/supabase-js`, everywhere); CI verifies tokens with a test key pair, no network.
- A hosted dependency: Supabase project keys live in `.env` (rule 8); the web's origin joins
  the API's CORS list from the environment when it is hosted (roadmap H1).
- The CLIs and the nightly are unaffected (they run as `site` / `ALGOTRADE_USER` locally).
- The token protects the API on the network, not the Parquet files on its host: hosting (H1)
  owns the disk, HTTPS and the process, and is a separate decision.
