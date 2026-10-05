/**
 * Trader > Explore end to end, against the production build with the API mocked from
 * recorded fixtures (explore-api.ts): the ticker table over the full universe one server page
 * per request (sorted, filtered and paged by the server), the compare set and detail tabs, URL
 * state (shareable links) and accessibility in dark and light.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockApi } from './mock-api';

const COMPARE = '/explore?sel=AAPL,MSFT,NVDA';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  return errors;
}

async function useTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
  }, theme);
}

const tickers = (page: Page) => page.getByRole('grid', { name: 'Tickers' });
const summary = (page: Page) => page.getByText(/^[\d,]+ tickers? ·/);

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

for (const theme of ['dark', 'light'] as const) {
  test(`compare AAPL, MSFT and NVDA (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto(COMPARE);
    await expect(page.getByRole('heading', { level: 1, name: 'Explore' })).toBeVisible();
    await expect(summary(page)).toHaveText('11,427 tickers · 3 selected');
    for (const symbol of ['AAPL', 'MSFT', 'NVDA']) {
      await expect(
        page.getByRole('button', { name: `Remove ${symbol} from compare` }),
      ).toBeVisible();
    }
    await expect(
      page.getByRole('heading', { name: 'Performance · rebased to 100 · 1Y' }),
    ).toBeVisible();
    const side = page.getByRole('grid', { name: 'Side by side' });
    await expect(side.getByRole('button', { name: 'Close', exact: true })).toBeVisible();
    await expect(side.getByText('$333.69')).toBeVisible();
    await expect(side.getByText('NVDA', { exact: true })).toBeVisible();
    await useTheme(page, theme);
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });

  test(`options chain, simple and pro (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto(`${COMPARE}&tab=options`);
    await expect(
      page.getByRole('heading', { name: /AAPL options · 20 Nov · 49d · puts/ }),
    ).toBeVisible();
    const chain = page.getByRole('grid', { name: /AAPL puts/ });
    await expect(chain.getByText('8–15 Δ').first()).toBeVisible();
    await expect(chain.getByText(/Get paid .* now; buy 100 AAPL at/).first()).toBeVisible();
    await expect(chain.getByRole('columnheader', { name: /Delta/ })).toHaveCount(0);
    await page.getByRole('radio', { name: 'Pro' }).click();
    await expect(page).toHaveURL(/view=pro/);
    await expect(chain.getByRole('columnheader', { name: /Delta/ })).toBeVisible();
    await useTheme(page, theme);
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('one ticker opens on its overview', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/explore?sel=AAPL');
  await expect(page.getByRole('tab', { name: 'Overview' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByRole('heading', { name: 'AAPL · overview' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'AAPL headline numbers' })).toContainText(
    'Market cap',
  );
  await page.getByRole('tab', { name: 'Compare' }).click();
  await expect(page).toHaveURL(/tab=compare/);
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('the tabs, the compare set and the columns live in the URL', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto(COMPARE);
  await expect(summary(page)).toBeVisible();
  await page.getByRole('tab', { name: 'Events' }).click();
  await expect(page).toHaveURL(/tab=events/);
  await expect(page.getByRole('grid', { name: 'AAPL events' }).getByText('Earnings')).toBeVisible();
  await page.getByRole('button', { name: 'Remove MSFT from compare' }).click();
  await expect(page).toHaveURL(/sel=AAPL%2CNVDA|sel=AAPL,NVDA/);
  await page.reload();
  await expect(page.getByRole('tab', { name: 'Events' })).toHaveAttribute('aria-selected', 'true');
  await expect(summary(page)).toHaveText(/2 selected/);
  await page.getByRole('tab', { name: 'Features' }).click();
  await expect(page.getByRole('grid', { name: 'AAPL features' })).toBeVisible();
  await page.getByRole('tab', { name: 'Screener hits' }).click();
  const hits = page.getByRole('region', { name: 'Screener hits' });
  await expect(hits).toContainText('VRP scanner');
  await expect(hits).toContainText('Watch');
  await page.goto('/explore?cols=feature.market_cap,instrument.sector&sort=-feature.market_cap');
  await expect(tickers(page).getByRole('columnheader', { name: /Mkt cap/ })).toHaveAttribute(
    'aria-sort',
    'descending',
  );
  await expect(tickers(page).getByRole('columnheader', { name: /Sector/ })).toBeVisible();
  await expect(tickers(page).getByRole('columnheader', { name: /IV30/ })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('ticking a row adds it to the compare set', async ({ page }) => {
  await page.goto('/explore');
  await expect(summary(page)).toHaveText('11,427 tickers · 0 selected');
  await page.getByRole('searchbox', { name: 'Filter tickers' }).fill('AAPL');
  await tickers(page).getByRole('checkbox', { name: 'Select AAPL', exact: true }).check();
  await expect(page).toHaveURL(/sel=AAPL/);
  await expect(page.getByRole('button', { name: 'Remove AAPL from compare' })).toBeVisible();
});

test('one server page per request: sort, search and paging', async ({ page }) => {
  const errors = collectErrors(page);
  const asked: Record<string, unknown>[] = [];
  page.on('request', (request) => {
    const body = request.postData();
    if (request.url().endsWith('/api/graphql') && body?.includes('query FeatureTable')) {
      asked.push((JSON.parse(body) as { variables: Record<string, unknown> }).variables);
    }
  });
  await page.goto('/explore');
  await expect(summary(page)).toHaveText('11,427 tickers · 0 selected');
  await expect(page.getByText('Page 1 of 115')).toBeVisible();
  expect(asked).toHaveLength(1); // the whole universe in one page request, not 12
  expect(asked[0]).toMatchObject({ page: 1, size: 100, sort: null });
  const grid = tickers(page);
  const close = grid.getByRole('button', { name: 'Close', exact: true });
  await close.click();
  await expect(page).toHaveURL(
    /sort=-rollup\.price_stats%40v2\.close|sort=-rollup\.price_stats@v2\.close/,
  );
  const header = page.getByRole('button', { name: 'Close', exact: true });
  await expect(grid.getByRole('columnheader').filter({ has: header })).toHaveAttribute(
    'aria-sort',
    'descending',
  );
  expect(asked.at(-1)).toMatchObject({ sort: '-rollup.price_stats@v2.close', page: 1 });
  await expect(grid.getByText('MSFT', { exact: true })).toBeVisible(); // $517.53 is the top
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page.getByText('Page 2 of 115')).toBeVisible();
  expect(asked.at(-1)).toMatchObject({ page: 2 });
  await page.getByRole('searchbox', { name: 'Filter tickers' }).fill('NVDA');
  await expect(summary(page)).toHaveText(/^1 ticker ·/);
  expect(asked.at(-1)).toMatchObject({ q: 'NVDA', page: 1 });
  await expect(grid.getByText('NVDA', { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
