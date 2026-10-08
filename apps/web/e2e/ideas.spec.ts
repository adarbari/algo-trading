/**
 * Trader > Ideas end to end, against the production build with the API mocked from
 * fixtures shaped like the `IdeasPage` GraphQL response (ideas-api.ts): the ranked table with
 * its screener chips, earnings (next, else the last date) and earnings-before-expiry flag,
 * the preset views and filter chips (kept in the URL), opening tickers in Explore with the
 * screener that surfaced them, accessibility.
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

const grid = (page: Page) => page.getByRole('grid', { name: 'Top ideas' });

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

for (const theme of ['dark', 'light'] as const) {
  test(`the ideas are listed (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto('/ideas');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Ideas for Fri 2 Oct' }),
    ).toBeVisible();
    await expect(page.getByRole('list', { name: 'Screener priority' })).toHaveCount(0);
    const aapl = grid(page).getByRole('row', { name: /AAPL/ });
    await expect(aapl).toContainText('Short premium liquidity');
    await expect(aapl).toContainText('Earnings first');
    await expect(grid(page).getByRole('row', { name: /NVDA/ })).not.toContainText('Earnings first');
    await expect(grid(page).getByRole('row', { name: /NVDA/ })).toContainText('Last 27 Aug');
    await expect(aapl).toContainText('Thu 29 Oct');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a field header in Top ideas opens its Guide drawer', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  const header = grid(page).getByRole('columnheader', { name: /IV30/ }).first();
  await header.getByRole('button', { name: /^What is .*\?$/ }).click();
  await expect(page.getByRole('dialog')).toContainText('feature.vrp_iv30');
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('a preset view and the filter chips narrow the table and live in the URL', async ({
  page,
}) => {
  await page.goto('/ideas');
  await expect(page.getByRole('button', { name: 'Clear filters' })).toHaveCount(0);
  await page.getByRole('button', { name: 'High conviction' }).click();
  await expect(page).toHaveURL(/view=conviction/);
  await expect(grid(page).getByRole('row', { name: /KO/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Top today' }).click();

  await page.getByRole('button', { name: 'Liquidity', exact: true }).click();
  await page.getByRole('button', { name: 'Liquidity risk', exact: true }).click();
  await expect(page).toHaveURL(/liq=risk/);
  await expect(grid(page).getByRole('row', { name: /KO/ })).toBeVisible();
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toHaveCount(0);

  await page.getByRole('button', { name: 'Screener', exact: true }).click();
  await page.getByRole('button', { name: 'VRP scanner', exact: true }).click();
  await expect(
    page.getByText(/No idea matches Screener: VRP scanner · Liquidity: Liquidity risk/),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Remove Screener: VRP scanner' }).click();
  await page.getByRole('button', { name: 'Clear filters' }).first().click();
  await expect(page).not.toHaveURL(/liq=/);
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
});

test('a link with filters opens the filtered table', async ({ page }) => {
  await page.goto('/ideas?decision=EVENT_RISK');
  await expect(grid(page).getByRole('row', { name: /TSLA/ })).toBeVisible();
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Remove Decision: Event risk' })).toBeVisible();
});

test('shows the stored display values and the watch-outs', async ({ page }) => {
  await page.goto('/ideas');
  // A retrying assertion: a one-shot read of the headers can run before the grid mounts.
  await expect(grid(page).getByRole('columnheader')).toContainText([
    'IV30',
    'HV30',
    'IV / HV',
    'Put strike',
    'Put ROC',
  ]);
  const aapl = grid(page).getByRole('row', { name: /AAPL/ });
  await expect(aapl).toContainText('31.0%');
  await expect(aapl).toContainText('1.49');
  await expect(aapl).toContainText('Earnings before expiry');
  await expect(grid(page).getByRole('row', { name: /KO/ })).toContainText('Leveraged / inverse');
  await expect(grid(page).getByRole('row', { name: /KO/ })).toContainText('Liquidity risk');
  await expect(grid(page).getByRole('row', { name: /TSLA/ })).toContainText('Large move');
});

test('shows the size the regime allows and lists the paused picks with their reason', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await expect(grid(page).getByRole('columnheader')).toContainText(['Size']);
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toContainText('50%');
  const paused = page.getByRole('button', { name: /Paused by regime/ });
  await expect(paused).toHaveAttribute('aria-expanded', 'false');
  await expect(paused).toContainText('(1)');
  await paused.click();
  await expect(page.getByText('regime=STRESS: vrp-scanner pauses in STRESS')).toBeVisible();
  await expectAccessible(page);
  expect(errors).toEqual([]);
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
  await expect(page).toHaveURL(/via=short-premium-liquidity/);
});
