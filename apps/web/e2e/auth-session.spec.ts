/**
 * The browser session on `@supabase/auth-js` (ADR 0040, amended): sign-in posts the password
 * grant to `/auth/v1/token`; the session lives in localStorage under `sb-<project ref>-auth-token`
 * (the key supabase-js used, so existing sessions survive); the API calls carry the bearer; an
 * expired token is refreshed through the refresh grant; sign-out is local scope and, in one
 * tab, ends the session in the other at once (auth-js broadcasts it; auth.ts routes it to onUnauthorized).
 */
import { expect, test, type Page } from '@playwright/test';

import { SUPABASE_URL, TOKEN, mockSupabase, mockViewer } from './auth-api';
import { mockApi } from './mock-api';

const STORAGE_KEY = 'sb-127-auth-token'; // the host's first label: 127.0.0.1

interface Stub {
  grants: string[];
  logouts: string[];
  refreshTokens: string[];
}

async function withAuth(page: Page): Promise<Stub> {
  const stub: Stub = { grants: [], logouts: [], refreshTokens: [] };
  await mockApi(page);
  await mockViewer(page, { role: 'trader', requireToken: true });
  await mockSupabase(page);
  // Added last, so tried first: record every token grant, answer the refresh grant.
  await page.route(`${SUPABASE_URL}/auth/v1/token*`, async (route) => {
    const url = new URL(route.request().url());
    const grant = url.searchParams.get('grant_type') ?? '';
    stub.grants.push(grant);
    if (grant !== 'refresh_token') {
      await route.fallback();
      return;
    }
    const sent = route.request().postDataJSON() as { refresh_token: string };
    stub.refreshTokens.push(sent.refresh_token);
    await route.fulfill({
      json: {
        access_token: TOKEN,
        token_type: 'bearer',
        expires_in: 3600,
        expires_at: Math.floor(Date.now() / 1000) + 3600,
        refresh_token: 'e2e-refresh-token-2',
        user: { id: 'u-1', aud: 'authenticated', email: 'tess@example.com', app_metadata: {} },
      },
    });
  });
  await page.route(`${SUPABASE_URL}/auth/v1/logout*`, async (route) => {
    stub.logouts.push(new URL(route.request().url()).searchParams.get('scope') ?? '');
    await route.fulfill({ status: 204 });
  });
  return stub;
}

async function signIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel(/Email/).fill('tess@example.com');
  await page.getByLabel(/Password/).fill('pw');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/ideas$/);
}

const stored = (page: Page) =>
  page.evaluate((key) => {
    const raw = window.localStorage.getItem(key);
    return raw === null ? null : (JSON.parse(raw) as Record<string, unknown>);
  }, STORAGE_KEY);

test('sign-in uses the password grant, stores the session under sb-<ref>-auth-token, sends the bearer', async ({
  page,
}) => {
  const stub = await withAuth(page);
  const bearers: (string | undefined)[] = [];
  page.on('request', (request) => {
    if (request.url().endsWith('/api/graphql')) bearers.push(request.headers()['authorization']);
  });
  await signIn(page);
  expect(stub.grants).toEqual(['password']);
  const session = await stored(page);
  expect(session).toMatchObject({ access_token: TOKEN, refresh_token: 'e2e-refresh-token' });
  expect(await page.evaluate(() => Object.keys(window.localStorage))).toEqual([STORAGE_KEY]);
  expect(bearers.length).toBeGreaterThan(0);
  // Before sign-in the login page sends none; every call after it carries the token.
  expect(bearers.at(-1)).toBe(`Bearer ${TOKEN}`);
  expect(bearers.filter((value) => value !== undefined && value !== `Bearer ${TOKEN}`)).toEqual([]);
});

test('an expired token is refreshed with the refresh token', async ({ page }) => {
  const stub = await withAuth(page);
  await signIn(page);
  await page.evaluate((key) => {
    const session = JSON.parse(window.localStorage.getItem(key) ?? '{}') as Record<string, unknown>;
    session['expires_at'] = Math.floor(Date.now() / 1000) - 60;
    window.localStorage.setItem(key, JSON.stringify(session));
  }, STORAGE_KEY);
  await page.reload();
  await expect(page).toHaveURL(/\/ideas$/);
  await expect(page.getByText('Tess Trader')).toBeVisible();
  expect(stub.refreshTokens).toEqual(['e2e-refresh-token']);
  expect(await stored(page)).toMatchObject({ refresh_token: 'e2e-refresh-token-2' });
});

test('sign-out is local scope (this session only) and removes the stored session', async ({
  page,
}) => {
  const stub = await withAuth(page);
  await signIn(page);
  await page.getByRole('button', { name: 'Tess Trader' }).click();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(stub.logouts).toEqual(['local']);
  expect(await stored(page)).toBeNull();
});

test('signing out in one tab ends the session in the other at once', async ({ page, context }) => {
  await withAuth(page);
  await signIn(page);
  const other = await context.newPage();
  await withAuth(other);
  await other.goto('/ideas');
  await expect(other).toHaveURL(/\/ideas$/);
  await page.getByRole('button', { name: 'Tess Trader' }).click();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  // A tab in the background renders when it is shown; the session is already gone from storage.
  await other.bringToFront();
  await expect(other).toHaveURL(/\/login$/);
});

test('signing out then in again in one tab leaves the other tab signed in when it returns', async ({
  page,
  context,
}) => {
  await withAuth(page);
  await signIn(page);
  const other = await context.newPage();
  await withAuth(other);
  await other.goto('/ideas');
  await expect(other.getByText('Tess Trader')).toBeVisible();
  await page.getByRole('button', { name: 'Tess Trader' }).click();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await other.bringToFront();
  await expect(other).toHaveURL(/\/login$/);
  await signIn(page);
  await other.goto('/ideas');
  await expect(other).toHaveURL(/\/ideas$/);
  await expect(other.getByText('Tess Trader')).toBeVisible();
});
