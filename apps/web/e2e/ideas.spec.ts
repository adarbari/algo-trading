/**
 * Trader > Ideas end to end, against the production build with the API mocked from
 * fixtures shaped like the `IdeasPage` GraphQL response (ideas-api.ts): the ranked table with
 * its screener chips, earnings (next, else the last date) and earnings-before-expiry flag,
 * the shared filter bar (group popovers, chips, zero-result recovery; kept in the URL), opening tickers in Explore with the
 * screener that surfaced them, accessibility.
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
    await expect(aapl).toContainText('Apple Inc. · XLK');
    await expect(aapl.getByRole('link', { name: 'VRP scanner' })).toHaveAttribute(
      'href',
      '/screeners/vrp-scanner',
    );
    await expect(aapl.getByRole('link', { name: 'Short premium liquidity' })).toHaveAttribute(
      'href',
      /^\/screeners\/[\w-]+$/,
    );
    await expect(aapl).not.toContainText('more');
    await expect(aapl).toContainText('226.80');
    await expect(aapl.getByRole('img', { name: /^Criteria: / })).toHaveAccessibleName(
      /Trend up: Passed, Iv rank: Near miss/,
    );
    await expect(grid(page).getByRole('row', { name: /NVDA/ })).toContainText('Last 27 Aug');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a field header in Top ideas opens its Guide drawer', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/ideas?columns=options');
  const header = grid(page).getByRole('columnheader', { name: /IV30/ }).first();
  await header.getByRole('button', { name: /^What is .*\?$/ }).click();
  await expect(page.getByRole('dialog')).toContainText('feature.vrp_iv30');
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('a group popover narrows the list on the server, the chips show what each removes, and the URL keeps it', async ({
  page,
}) => {
  await page.goto('/ideas');
  await expect(grid(page).getByRole('row', { name: /KO/ })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Applied filters' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Setup' }).click();
  await page
    .getByRole('list', { name: 'Decision' })
    .getByRole('button', { name: /^Qualified/ })
    .click();
  await expect(page).toHaveURL(/f=decision(%3A|:)QUALIFIED/);
  // The popover holds focus and hides the page behind it: close it to read the table.
  await page.keyboard.press('Escape');
  await expect(grid(page).getByRole('row', { name: /KO/ })).toHaveCount(0);
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  const chips = page.getByRole('group', { name: 'Applied filters' });
  await expect(chips).toContainText('Decision Qualified');
  await expect(chips).toContainText('removes 2');
  await expect(page.getByText('4 of 6').first()).toBeVisible();
  await chips.getByRole('button', { name: /^Decision Qualified/ }).click();
  await expect(page).toHaveURL(/f=(%21|!)decision/);
  await expect(grid(page).getByRole('row', { name: /KO/ })).toBeVisible();
  await page.getByRole('button', { name: 'Clear all' }).click();
  await expect(page).not.toHaveURL(/f=/);
});

test('a link with filters opens the filtered table', async ({ page }) => {
  await page.goto('/ideas?f=decision:EVENT_RISK');
  await expect(grid(page).getByRole('row', { name: /TSLA/ })).toBeVisible();
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toHaveCount(0);
  await expect(
    page
      .getByRole('group', { name: 'Applied filters' })
      .getByRole('button', { name: /^Decision Event risk, removes 5/ }),
  ).toBeVisible();
});

test('an empty result says what to switch off, and switching it off brings the rows back', async ({
  page,
}) => {
  await page.goto('/ideas?f=decision:EVENT_RISK;agreeing:3..');
  await expect(page.getByText('No ideas match all 2 filters')).toBeVisible();
  await page.getByRole('button', { name: /^Switch off Agreeing screeners gives 1/ }).click();
  await expect(page).toHaveURL(/(%21|!)agreeing/);
  await expect(grid(page).getByRole('row', { name: /TSLA/ })).toBeVisible();
  await expectAccessible(page);
});

test('the column switch swaps the stock columns for the options set, kept in the URL', async ({
  page,
}) => {
  await page.goto('/ideas');
  await expect(grid(page).getByRole('columnheader')).toContainText([
    'Picked by',
    'Decision',
    'Watch out',
  ]);
  await page.getByRole('radio', { name: 'Options columns' }).click();
  await expect(page).toHaveURL(/columns=options/);
  const aapl = grid(page).getByRole('row', { name: /AAPL/ });
  await expect(aapl).toContainText('Earnings first');
  await expect(grid(page).getByRole('row', { name: /NVDA/ })).not.toContainText('Earnings first');
  await page.getByRole('radio', { name: 'Stocks columns' }).click();
  await expect(page).not.toHaveURL(/columns=/);
});

test('shows the stored display values and the watch-outs', async ({ page }) => {
  await page.goto('/ideas?columns=options');
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

test('lists what the followed edges say to buy and sell above the table', async ({ page }) => {
  const trade = (symbol: string) => ({
    edgeId: 'drift',
    edgeName: 'Drift',
    instrumentId: `EQ:${symbol}`,
    instrument: { symbol },
    rank: 1,
    buySession: '2026-10-05',
    sellSession: '2026-11-02',
  });
  await mockIdeasApi(page, {
    data: {
      edgeDesk: {
        session: '2026-10-02',
        sellSession: '2026-10-05',
        buys: [trade('MSFT')],
        sells: [trade('KO')],
        followed: [
          {
            edgeId: 'drift',
            name: 'Drift',
            state: 'following',
            tonight: 'signalled',
            tonightReason: '',
            missed: [],
            record: { state: 'on_track', closed: 20, open: 2, winRate: 0.6 },
          },
        ],
      },
    },
  });
  const errors = collectErrors(page);
  await page.goto('/ideas');
  const buys = page.getByRole('grid', { name: 'Buy next session' });
  await expect(buys.getByText('MSFT')).toBeVisible();
  await expect(page.getByRole('grid', { name: 'Sell next session' }).getByText('KO')).toBeVisible();
  await expect(
    page.getByRole('grid', { name: 'Followed edges' }).getByText('On track'),
  ).toBeVisible();
  await expectAccessible(page);
  expect(errors).toEqual([]);
});
