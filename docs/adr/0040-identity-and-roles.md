# ADR 0040: Users are declared in a site registry with a role; the API authenticates them with a local login and a session cookie

**Status:** accepted (2026-10-05; owner decision; implementation: roadmap ID1-ID4). Closes the
open decision "User identity scheme" (phase 4) and extends [0015](0015-configs-selections-users.md)
(users as labels), [0024](0024-api.md), [0029](0029-rule-screener.md) (`?user=` on writes),
[0025](0025-frontend-architecture.md) (the role-gating seam `guard.ts`) and
[0037](0037-domain-read-model-served-by-graphql.md) (what stays REST).

## Context
Users exist only as labels: `ALGOTRADE_USER` picks the one user the API serves, a write names
any user with `?user=`, and every workspace is open (`canEnter` returns true). Configs are
already per user on disk (`config/users/<id>/`, ADR 0015) and every service is user-scoped
through `UserContext`, so the missing pieces are: who exists, what they may do, and how the
API knows who is calling. The app runs on one machine for a handful of people; an identity
provider (OAuth, SSO) is more than it needs and would add a network dependency to a local tool.

## Decision
1. **A site registry of users with a role.** `config/site/users.toml` (`[[user]]` with `id`,
   `role`, `name`) typed by the one settings loader into `UsersSettings`
   (`config/site/users.py`). Roles are `admin` (TRADER and ADMIN workspaces, the ops reads,
   waivers, writes for any user) and `trader` (TRADER only, writes for themselves). Without
   the file the install is single-user: `local` and `site` are admins, so today's behaviour is
   unchanged. At least one admin must exist; an unknown id is refused everywhere.
2. **Configs belong to the registry's users.** A user's configs stay in `config/users/<id>/`;
   `services/authoring` writes only for a declared user, and the `?user=` query parameter is
   replaced by the authenticated user (an admin may still name another user).
3. **Local login, session cookie.** `POST /auth/login` (user id + password) and
   `POST /auth/logout` are REST writes. Password hashes live in
   `config/users/<id>/credentials.toml` (git-ignored, written by
   `algotrade-api users set-password <id>`, argon2 via `pwdlib`); the API signs an HttpOnly,
   SameSite=Strict session cookie with `ALGOTRADE_SESSION_SECRET` (env only, rule 8). Every
   REST and GraphQL request resolves its user from the cookie once (`deps.py`,
   `graphql/context.py`); without a session the API answers 401. Dev shortcut: when no
   `users.toml` exists the API serves `ALGOTRADE_USER` without login, as today.
4. **The web learns who is calling from one field.** `Query.viewer { id name role workspaces }`
   (a page read: GraphQL, not REST). `guard.ts` stays the one role-gating seam and reads it;
   a refused workspace redirects to the default; a 401 shows the login page (a design-system
   `LoginForm` component first, then the page). Ops fields and the ADMIN workspace require
   `admin`; the server enforces it, the guard only hides.
5. **Not now:** OAuth / SSO, API tokens for scripts (the CLIs keep `ALGOTRADE_USER` on the
   machine that holds the data), per-user data visibility (IB-B stays its own item).

## Consequences
- One new site settings file and one new module; `UserContext` gains nothing until ID3 (the
  resolved user and role become fields on it then).
- Two new REST writes (`/auth/login`, `/auth/logout`) and no new GET: the allow-list does not
  grow. `?user=` on writes retires in ID3 (the web client regenerates).
- The CLIs and the nightly are unaffected (they run as `site` / `ALGOTRADE_USER` locally).
- A compromised machine still exposes the data: the cookie protects the API on the network,
  not the Parquet files. That is the same trust boundary as today.
