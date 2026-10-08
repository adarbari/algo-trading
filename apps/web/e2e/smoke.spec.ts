/**
 * Smoke test: the production build boots, `/` opens the TRADER workspace home (Ideas), the
 * ADMIN workspace is reachable, the top bar's workspace switch and section links navigate, and
 * both workspaces are accessible in dark (the default) and light.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockApi } from './mock-api';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  return errors;
}

/** The app is dark-first (UiProvider); light is the same tokens under data-theme="light". */
async function useTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
  }, theme);
}

// Every page the smoke test opens gets its API answered from recorded fixtures.
test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

for (const theme of ['dark', 'light'] as const) {
  test(`/ opens the trader workspace on Ideas (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto('/');
    await expect(page).toHaveURL(/\/ideas$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Ideas' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Trader sections' })).toContainText(
      'Explore',
    );
    await useTheme(page, theme);
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });

  test(`the admin workspace is reachable (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto('/admin/ingestion');
    await expect(page.getByRole('heading', { level: 1, name: 'Ingestion' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Admin sections' })).toContainText(
      'Users & configs',
    );
    await useTheme(page, theme);
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('the top bar switches workspace and section', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await expect(page.getByRole('link', { name: 'Ideas' })).toHaveAttribute('aria-current', 'page');
  await page.getByRole('link', { name: 'Explore' }).click();
  await expect(page).toHaveURL(/\/explore$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Explore' })).toBeVisible();
  // The workspace switch lives in the account menu (the viewer's name), not in the bar.
  await expect(page.getByRole('radio', { name: 'Admin' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Abhi Admin' }).click();
  await page.getByRole('radio', { name: 'Admin' }).click();
  await expect(page).toHaveURL(/\/admin\/ingestion$/);
  await page.getByRole('button', { name: 'Abhi Admin' }).click();
  await expect(page.getByRole('radio', { name: 'Admin' })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('radio', { name: 'Admin' }).press('ArrowLeft');
  await expect(page).toHaveURL(/\/ideas$/);
  expect(errors).toEqual([]);
});
