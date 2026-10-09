/**
 * Trader > Explore end to end, against the production build with the API mocked from
 * recorded fixtures (explore-api.ts): the ticker search (type-ahead over the universe, `/`,
 * arrows and Enter), open tickers as closable tabs, the detail tabs of the selected one, the
 * "Why it is an idea" tab for a ticker Ideas opened, URL state (shareable links) and
 * accessibility in dark and light.
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

const open = (page: Page) => page.getByRole('tablist', { name: 'Open tickers' });
const view = (page: Page) => page.getByRole('tablist', { name: 'View' });

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

for (const theme of ['dark', 'light'] as const) {
  test(`compare AAPL, MSFT and NVDA (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto(COMPARE);
    await expect(page.getByRole('heading', { level: 1, name: 'Explore' })).toBeVisible();
    await expect(open(page).getByRole('tab')).toHaveText(['AAPL', 'MSFT', 'NVDA']);
    await expect(view(page).getByRole('tab', { name: 'Compare' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
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

test('with nothing open the page asks for a ticker', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/explore');
  await expect(page.getByText('No ticker open')).toBeVisible();
  await expect(open(page)).toHaveCount(0);
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('one ticker opens on its overview', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/explore?sel=AAPL');
  await expect(view(page).getByRole('tab', { name: 'Overview' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(view(page).getByRole('tab', { name: 'Compare' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'AAPL · overview' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'AAPL headline numbers' })).toContainText(
    'Market cap',
  );
  await expect(page.getByLabel('In rough markets')).toContainText('Tariff shock, spring 2025');
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('search adds a ticker as a tab: type, arrows, Enter; / focuses the box', async ({ page }) => {
  await page.goto('/explore?sel=AAPL');
  const box = page.getByRole('combobox', { name: 'Search tickers' });
  await expect(box).toBeVisible();
  await page.keyboard.press('/');
  await expect(box).toBeFocused();
  await box.fill('nvda');
  const options = page.getByRole('option');
  await expect(options.first()).toContainText('NVDA');
  await expectAccessible(page);
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/sel=AAPL%2CNVDA|sel=AAPL,NVDA/);
  await expect(page).toHaveURL(/focus=NVDA/);
  await expect(open(page).getByRole('tab')).toHaveText(['AAPL', 'NVDA']);
  await expect(open(page).getByRole('tab', { name: 'NVDA' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(box).toHaveValue('');
  // Escape closes the list and leaves the box.
  await box.fill('msft');
  await expect(options.first()).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(options).toHaveCount(0);
  // No console-error check: the mocks record only AAPL's detail reads, so NVDA's 404.
});

test('the tabs and the open tickers live in the URL; a closed tab leaves the list', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto(`${COMPARE}&focus=AAPL`);
  await view(page).getByRole('tab', { name: 'Events' }).click();
  await expect(page).toHaveURL(/tab=events/);
  await expect(page.getByRole('grid', { name: 'AAPL events' }).getByText('Earnings')).toBeVisible();
  await open(page).getByRole('tab', { name: 'MSFT' }).focus();
  await page.keyboard.press('Delete');
  await expect(page).toHaveURL(/sel=AAPL%2CNVDA|sel=AAPL,NVDA/);
  await page.reload();
  await expect(open(page).getByRole('tab')).toHaveText(['AAPL', 'NVDA']);
  await expect(view(page).getByRole('tab', { name: 'Events' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.getByLabel('Close NVDA').click({ force: true });
  await expect(open(page).getByRole('tab')).toHaveText(['AAPL']);
  await expect(page).toHaveURL(/sel=AAPL(&|$)/);
  await view(page).getByRole('tab', { name: 'Features' }).click();
  await expect(page.getByRole('grid', { name: 'AAPL features' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('a ticker Ideas opened shows why it is an idea, from the screener that surfaced it', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/explore?sel=AAPL&focus=AAPL&via=vrp_scanner');
  const why = view(page).getByRole('tab', { name: 'Why it is an idea' });
  await expect(why).toBeVisible();
  await why.click();
  const panel = page.getByRole('region', { name: 'Why it is an idea' });
  await expect(panel).toContainText('Watch');
  await expect(panel).toContainText('#3');
  await expect(panel).toContainText('iv_hv_ratio 1.10 below 1.25');
  await expect(panel.getByRole('button', { name: 'Open VRP scanner' })).toBeVisible();
  await expectAccessible(page);
  // Another tab of the ticker, then another ticker: the Why tab goes with the screener.
  await page.goto('/explore?sel=AAPL');
  await expect(view(page).getByRole('tab', { name: 'Why it is an idea' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'AAPL · overview' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('the screener hits tab lists the screeners that picked the ticker', async ({ page }) => {
  await page.goto('/explore?sel=AAPL&tab=hits');
  const hits = page.getByRole('region', { name: 'Screener hits' });
  await expect(hits).toContainText('VRP scanner');
  await expect(hits).toContainText('Watch');
});
