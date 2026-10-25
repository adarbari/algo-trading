/**
 * The Light / Dark / System choice (ADR 0085): the device's copy sets the theme before the app
 * runs, the stored choice replaces it once known, and the account menu's control applies a change
 * at once and saves it (`PUT /preferences/appearance`).
 */
import { expect, test, type Page } from '@playwright/test';

import { mockApi } from './mock-api';

const LIGHT_BG = '#f4f6fb';

/** The stored theme the API answers (registered after `mockApi`, so it is tried first). */
async function storedTheme(page: Page, theme: string): Promise<void> {
  await page.route('**/api/graphql', async (route) => {
    const body = route.request().postDataJSON() as { query?: string } | null;
    if (!/query\s+Appearance\b/.test(body?.query ?? '')) {
      await route.fallback();
      return;
    }
    await route.fulfill({ json: { data: { appearance: { theme } } } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test('the device copy sets the theme before the app runs', async ({ page }) => {
  await storedTheme(page, 'light');
  await page.addInitScript(() => {
    window.localStorage.setItem('algotrade.theme', 'light');
  });
  await page.goto('/ideas', { waitUntil: 'commit' });
  await page.waitForFunction(() => document.documentElement.hasAttribute('data-theme'));
  const background = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim(),
  );
  expect(background).toBe(LIGHT_BG);
});

test('System follows the device; a choice in the account menu applies and is saved', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await storedTheme(page, 'system');
  let saved: unknown;
  await page.route('**/api/preferences/appearance', async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill({ json: { theme: 'dark' } });
  });
  await page.goto('/ideas');
  await expect(page.getByRole('heading', { level: 1, name: 'Ideas' })).toBeVisible();
  const background = () =>
    page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim(),
    );
  await expect.poll(background).toBe(LIGHT_BG);

  await page.getByRole('button', { name: /Abhi Admin/ }).click();
  await page.getByRole('radio', { name: 'Dark' }).click();
  await expect.poll(background).not.toBe(LIGHT_BG);
  await expect.poll(() => saved).toEqual({ theme: 'dark' });
  expect(await page.evaluate(() => window.localStorage.getItem('algotrade.theme'))).toBe('dark');
});
