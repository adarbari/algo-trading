/**
 * Trader > Regime end to end, against the production build with the regime mocked from
 * fixtures recorded from the real API (regime-api.ts): until the RG3 groups exist the regime
 * is UNKNOWN with its reason, every indicator card is listed (slow and fast) and the reading
 * list shows each link once. The top-bar chip says "not computed" on every page and opens the
 * Regime page; the Ideas strip says the sizing rule; accessibility in both themes.
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

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

for (const theme of ['dark', 'light'] as const) {
  test(`the Regime page shows the UNKNOWN state, the cards and the reading list (${theme})`, async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.goto('/regime');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'Regime' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 3, name: 'Not computed' })).toBeVisible();
    await expect(page.getByText(/the regime has not been computed yet/).first()).toBeVisible();
    const slow = page.getByRole('region', { name: 'Slow-moving warning signs' });
    const fast = page.getByRole('region', { name: 'Fast-moving market signs' });
    await expect(slow.getByRole('listitem')).toHaveCount(5);
    await expect(fast.getByRole('listitem')).toHaveCount(3);
    const reading = page.getByRole('region', { name: 'Reading list' });
    await expect(reading.getByRole('link').first()).toBeVisible();
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a card opens to its detail and its links', async ({ page }) => {
  await page.goto('/regime');
  await page.getByRole('button', { name: /Are long-term rates below short-term ones/ }).click();
  await expect(page.getByRole('heading', { name: 'What it did before' })).toBeVisible();
  await expect(page.getByRole('link', { name: /FRED/ }).first()).toBeVisible();
});

test('the top-bar chip says not computed and opens the Regime page; Ideas shows the strip', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await expect(page.getByText('New positions sized at 100% (regime not computed)')).toBeVisible();
  await page.getByRole('button', { name: 'Regime: not computed' }).first().click();
  await expect(page).toHaveURL(/\/regime$/);
  await expect(page.getByRole('link', { name: 'Regime' })).toHaveAttribute('aria-current', 'page');
  expect(errors).toEqual([]);
});
