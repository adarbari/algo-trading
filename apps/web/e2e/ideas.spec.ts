/**
 * Trader > Ideas end to end, against the production build with the API mocked from
 * fixtures shaped like GET /ideas (ideas-api.ts): the ranked table with its screener chips and
 * earnings-before-expiry flag, decision filters, opening tickers in Explore, reordering the
 * screeners (saved, and rolled back with a toast when the save fails), accessibility.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockIdeasApi } from './ideas-api';
import { mockApi } from './mock-api';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  return errors;
}

const grid = (page: Page) => page.getByRole('grid', { name: 'Top ideas' });
const screeners = (page: Page) => page.getByRole('list', { name: 'Screener priority' });

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

for (const theme of ['dark', 'light'] as const) {
  test(`the ideas and the screeners are listed (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto('/ideas');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Ideas for Fri 2 Oct' }),
    ).toBeVisible();
    await expect(screeners(page).getByRole('listitem')).toHaveCount(3);
    await expect(screeners(page).getByRole('listitem').first()).toContainText('VRP scanner');
    const aapl = grid(page).getByRole('row', { name: /AAPL/ });
    await expect(aapl).toContainText('Short premium liquidity');
    await expect(aapl).toContainText('Earnings first');
    await expect(grid(page).getByRole('row', { name: /NVDA/ })).not.toContainText('Earnings first');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('filters by decision', async ({ page }) => {
  await page.goto('/ideas');
  await page.getByRole('button', { name: 'Event risk' }).click();
  await expect(grid(page).getByRole('row', { name: /TSLA/ })).toBeVisible();
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toHaveCount(0);
});

test('shows the stored display values and the watch-outs', async ({ page }) => {
  await page.goto('/ideas');
  const headers = await grid(page).getByRole('columnheader').allTextContents();
  expect(headers.join(' | ')).toMatch(/IV30.*HV30.*IV \/ HV.*Put strike.*Put ROC/);
  const aapl = grid(page).getByRole('row', { name: /AAPL/ });
  await expect(aapl).toContainText('31.0%');
  await expect(aapl).toContainText('1.49');
  await expect(aapl).toContainText('Earnings before expiry');
  await expect(grid(page).getByRole('row', { name: /KO/ })).toContainText('Leveraged / inverse');
  await expect(grid(page).getByRole('row', { name: /KO/ })).toContainText('Liquidity risk');
  await expect(grid(page).getByRole('row', { name: /TSLA/ })).toContainText('Large move');
});

test('+ New screener opens the Builder', async ({ page }) => {
  await page.goto('/ideas');
  await page.getByRole('button', { name: '+ New screener' }).click();
  await expect(page).toHaveURL(/\/screeners\/new$/);
});

test('opens a ticker and a compare set in Explore', async ({ page }) => {
  await page.goto('/ideas');
  await grid(page)
    .getByRole('checkbox', { name: /Select MSFT/ })
    .check();
  await grid(page)
    .getByRole('checkbox', { name: /Select AAPL/ })
    .check();
  await page.getByRole('button', { name: 'Compare selected (2)' }).click();
  await expect(page).toHaveURL(/\/explore\?.*sel=MSFT%2CAAPL|sel=MSFT,AAPL/);
  await expect(page.getByRole('heading', { level: 1, name: 'Explore' })).toBeVisible();

  await page.goto('/ideas');
  await grid(page).getByRole('row', { name: /KO/ }).getByText('KO', { exact: true }).click();
  await expect(page).toHaveURL(/focus=KO/);
});

test('reordering the screeners saves the new priority', async ({ page }) => {
  const mock = await mockIdeasApi(page);
  await page.goto('/ideas');
  await page.getByRole('button', { name: 'Reorder VRP scanner' }).focus();
  await page.keyboard.press('Space');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Space');
  await expect(screeners(page).getByRole('listitem').first()).toContainText(
    'Short premium liquidity',
  );
  await expect
    .poll(() => mock.saved)
    .toEqual([['short-premium-liquidity', 'vrp-scanner', 'post-earnings-iv-crush']]);
});

test('a failed save puts the order back and says so', async ({ page }) => {
  await mockIdeasApi(page, { failSave: true });
  await page.goto('/ideas');
  await page.getByRole('button', { name: 'Reorder VRP scanner' }).focus();
  await page.keyboard.press('Space');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Space');
  await expect(page.getByText('Could not save the screener order')).toBeVisible();
  await expect(screeners(page).getByRole('listitem').first()).toContainText('VRP scanner');
});
