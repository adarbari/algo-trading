/**
 * Sign-in (ADR 0040) against the mocked API and a mocked Supabase: no session shows the login
 * page; wrong credentials say so; signing in opens the Ideas page with the viewer's name; a
 * trader never sees the ADMIN workspace and /admin sends them home; an unregistered account is
 * told to ask an admin; sign-out returns to the login page.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockViewer, mockSupabase, type Role } from './auth-api';
import { mockApi } from './mock-api';

async function withAuth(page: Page, role: Role, unregistered = false) {
  await mockApi(page);
  await mockViewer(page, { role, requireToken: true, unregistered });
  await mockSupabase(page);
}

async function signIn(page: Page, password = 'pw') {
  await page.getByLabel(/Email/).fill('tess@example.com');
  await page.getByLabel(/Password/).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

test('no session sends any page to the login page, which is accessible', async ({ page }) => {
  await withAuth(page, 'trader');
  await page.goto('/ideas');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Sign in to algotrade' })).toBeVisible();
  await expectAccessible(page);
});

test('wrong credentials show why and clear when the user edits', async ({ page }) => {
  await withAuth(page, 'trader');
  await page.goto('/login');
  await signIn(page, 'wrong');
  await expect(page.getByRole('alert')).toContainText('Wrong email or password.');
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel(/Password/).fill('wrong2');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('a trader signs in, lands on Ideas, has no Admin workspace, and signs out', async ({
  page,
}) => {
  await withAuth(page, 'trader');
  await page.goto('/login');
  await signIn(page);
  await expect(page).toHaveURL(/\/ideas$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Ideas' })).toBeVisible();
  await expect(page.getByText('Tess Trader')).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Trader' })).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Admin' })).toHaveCount(0);

  await page.goto('/admin/ingestion');
  await expect(page).toHaveURL(/\/ideas$/);

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/ideas');
  await expect(page).toHaveURL(/\/login$/);
});

test('an admin signs in and reaches the Admin workspace', async ({ page }) => {
  await withAuth(page, 'admin');
  await page.goto('/login');
  await signIn(page);
  await expect(page).toHaveURL(/\/ideas$/);
  await expect(page.getByRole('radio', { name: 'Admin' })).toBeVisible();
  await page.goto('/admin/ingestion');
  await expect(page.getByRole('heading', { level: 1, name: 'Ingestion' })).toBeVisible();
});

test('a valid sign-in the registry does not know is told to ask an admin', async ({ page }) => {
  await withAuth(page, 'trader', true);
  await page.goto('/login');
  await signIn(page);
  await expect(page.getByRole('alert')).toContainText(
    'Your account is not registered for this app; ask an admin',
  );
  await expect(page).toHaveURL(/\/login$/);
});

test('the session survives a reload', async ({ page }) => {
  await withAuth(page, 'trader');
  await page.goto('/login');
  await signIn(page);
  await expect(page).toHaveURL(/\/ideas$/);
  await page.reload();
  await expect(page).toHaveURL(/\/ideas$/);
  await expect(page.getByText('Tess Trader')).toBeVisible();
});
