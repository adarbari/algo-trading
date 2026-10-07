/**
 * The help drawer on a results-table header end to end (ADR 0051), against the production
 * build with the API mocked: a field column's header has an "i" button; it opens the field's
 * drawer (what it reads, what to use it for), "Open full page" goes to the field's Guide page,
 * and the drawer is accessible in both themes.
 */
import { expect, test } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockBuilderApi } from './builder-api';
import { mockApi } from './mock-api';

const IV30 = 'rollup.iv30@v1.iv30';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await mockBuilderApi(page);
});

for (const theme of ['dark', 'light'] as const) {
  test(`a results header opens the field's drawer (${theme})`, async ({ page }) => {
    await page.goto('/screeners/vrp_scanner');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    const header = page
      .getByRole('grid', { name: 'Screener results' })
      .getByRole('columnheader', { name: /IV30/ })
      .first();
    const help = header.getByRole('button', { name: /^What is .*\?$/ });
    await expect(help).toBeVisible();
    await help.click();

    const drawer = page.getByRole('dialog');
    await expect(drawer).toContainText(IV30);
    await expect(drawer).toContainText('30-day at-the-money implied volatility');
    await expect(drawer.getByRole('heading', { level: 3, name: 'Use it for' })).toBeVisible();
    await expect(drawer).toContainText('Rich premium to sell');
    await expectAccessible(page);
  });
}

test('Open full page goes to the field page', async ({ page }) => {
  await page.goto('/screeners/vrp_scanner');
  const header = page
    .getByRole('grid', { name: 'Screener results' })
    .getByRole('columnheader', { name: /IV30/ })
    .first();
  await header.getByRole('button', { name: /^What is .*\?$/ }).click();
  await page.getByRole('button', { name: 'Open full page' }).click();
  await expect(page).toHaveURL(/\/guide\/fields\/rollup\.iv30(%40|@)v1\.iv30$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
