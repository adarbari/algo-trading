/**
 * Playwright route mocks for who is calling (ADR 0040): `Query.viewer` on the mocked API and,
 * for the sign-in tests, Supabase's token endpoint. By default (`mockApi`) the API behaves as
 * with `ALGOTRADE_AUTH=off`: the viewer answers an admin with no token. `requireToken` makes it
 * answer like the real API with auth on: 401 without the bearer, 403 for a token the registry
 * does not know, the registry user otherwise.
 */
import type { Page, Route } from '@playwright/test';

export const SUPABASE_URL = 'http://127.0.0.1:54321';
export const SUPABASE_ANON_KEY = 'e2e-anon-key';
export const TOKEN = 'e2e-access-token';

export type Role = 'admin' | 'trader';

const VIEWERS = {
  admin: { id: 'abhi', name: 'Abhi Admin', role: 'admin', workspaces: ['trader', 'admin'] },
  trader: { id: 'tess', name: 'Tess Trader', role: 'trader', workspaces: ['trader'] },
} as const;

export interface ViewerMockOptions {
  /** The registry role the viewer has (default admin). */
  role?: Role;
  /** Answer like an API with auth on: needs `Authorization: Bearer <TOKEN>`. */
  requireToken?: boolean;
  /** With `requireToken`: the token is valid but the registry has no such user (403). */
  unregistered?: boolean;
  /** Answer this display name instead of the registry user's (a long one tests truncation). */
  name?: string;
}

export async function mockViewer(page: Page, options: ViewerMockOptions = {}): Promise<void> {
  const { role = 'admin', requireToken = false, unregistered = false, name } = options;
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as { query?: string } | null;
    // The status strip (every page) reads one operation: nothing wrong, so no strip and no 404s.
    if (/query\s+StatusStrip\b/.test(body?.query ?? '')) {
      await route.fulfill({ json: { data: { ideas: null } } });
      return;
    }
    // The saved page cache asks which session the API reads (entities/page-cache).
    if (/query\s+SessionDate\b/.test(body?.query ?? '')) {
      await route.fulfill({ json: { data: { session: { date: '2026-10-07' } } } });
      return;
    }
    if (!/query\s+Viewer\b/.test(body?.query ?? '')) {
      await route.fallback();
      return;
    }
    if (requireToken) {
      const signedIn = route.request().headers()['authorization'] === `Bearer ${TOKEN}`;
      if (!signedIn) {
        await route.fulfill({ status: 401, json: { detail: 'Not authenticated' } });
        return;
      }
      if (unregistered) {
        await route.fulfill({ status: 403, json: { detail: 'Not registered' } });
        return;
      }
    }
    await route.fulfill({
      json: { data: { viewer: { ...VIEWERS[role], ...(name === undefined ? {} : { name }) } } },
    });
  });
}

/** Supabase's password sign-in: `good` signs in, anything else is "Invalid login credentials". */
export async function mockSupabase(
  page: Page,
  good = { email: 'tess@example.com', password: 'pw' },
) {
  await page.route(`${SUPABASE_URL}/auth/v1/**`, async (route: Route) => {
    const url = route.request().url();
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204 });
      return;
    }
    if (url.includes('/token')) {
      const sent = route.request().postDataJSON() as { email: string; password: string };
      if (sent.email === good.email && sent.password === good.password) {
        await route.fulfill({
          json: {
            access_token: TOKEN,
            token_type: 'bearer',
            expires_in: 3600,
            expires_at: Math.floor(Date.now() / 1000) + 3600,
            refresh_token: 'e2e-refresh-token',
            user: { id: 'u-1', aud: 'authenticated', email: sent.email, app_metadata: {} },
          },
        });
        return;
      }
      await route.fulfill({
        status: 400,
        json: {
          code: 400,
          error_code: 'invalid_credentials',
          msg: 'Invalid login credentials',
        },
      });
      return;
    }
    await route.fulfill({ status: 204 });
  });
}
