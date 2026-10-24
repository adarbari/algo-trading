/**
 * Trader > Screeners > one screener (Results) end to end, against the production build with
 * the API mocked from fixtures shaped like GraphQL `ScreenerResults` (builder-api.ts): the latest
 * run as a review table (criterion columns in their units, a tinted near miss), the shared
 * filter bar (decision, since the previous run; zero-result recovery) and the user's view saved as they change it, the way to the Builder,
 * and the empty state of a screener with no run. Accessibility in both themes.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockBuilderApi } from './builder-api';
import { mockApi } from './mock-api';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !msg.text().includes('404')) errors.push(msg.text());
  });
  return errors;
}

const grid = (page: Page) => page.getByRole('grid', { name: 'Screener results' });

/**
 * Focus the grid once the run's rows are in. The grid is focusable while the results load (placeholder
 * rows, `aria-busy`), and the table drops a key pressed with no rows, so a key sent early is lost:
 * wait for the loaded rows first, never a fixed sleep.
 */
async function focusLoadedGrid(page: Page): Promise<void> {
  await expect(grid(page)).not.toHaveAttribute('aria-busy', 'true');
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  await grid(page).focus();
  await expect(grid(page)).toBeFocused();
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

for (const theme of ['dark', 'light'] as const) {
  test(`the latest run is a review table (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await mockBuilderApi(page);
    await page.goto('/screeners/vrp_scanner');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'vrp_scanner' })).toBeVisible();
    await expect(page.getByText('Run 2026-10-02 · changes since 2026-10-01')).toBeVisible();
    const dkng = grid(page).getByRole('row', { name: /AAPL/ });
    await expect(dkng).toContainText('Apple Inc.');
    await expect(dkng).toContainText('61.0%'); // IV30 in the catalogue's unit
    await expect(dkng).toContainText('New');
    await expect(page.getByText('Regime: Clouds building')).toBeVisible();
    // A pick the regime gate paused is listed, badged, never hidden.
    await expect(grid(page).getByRole('row', { name: /XOM/ })).toContainText('Paused');
    // SOXS missed IV/HV within tolerance: its cell is tinted, the value is still text.
    await expect(
      grid(page).getByRole('row', { name: /SOXS/ }).locator('[data-fill="warning"]'),
    ).toHaveText('1.08');
    await expect(
      grid(page).getByRole('row', { name: /RKT/ }).locator('[data-fill="negative"]'),
    ).toHaveText('0.90');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

/** Toggle one value of the Decision filter in the toolbar's Setup popover, then close it. */
async function toggleDecision(page: Page, name: RegExp): Promise<void> {
  await page.getByRole('button', { name: /^Setup/ }).click();
  await page.getByRole('list', { name: 'Decision' }).getByRole('button', { name }).click();
  await page.keyboard.press('Escape');
}

test('the run opens on the picks, the filter bar narrows it, and the view is saved as yours', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  await expect(page).toHaveURL(
    /f=decision(%3A|:)QUALIFIED%2CWATCH%2CLIQUIDITY_RISK%2CEVENT_RISK%2CPAUSED/,
  );
  expect(mock.tables.at(-1)?.['filters']).toMatchObject([
    { id: 'decision', values: ['QUALIFIED', 'WATCH', 'LIQUIDITY_RISK', 'EVENT_RISK', 'PAUSED'] },
  ]);
  await expect(page.getByRole('group', { name: 'Applied filters' })).toContainText(
    'Decision Qualified, Watch, Liquidity risk, Event risk, Paused',
  );
  await toggleDecision(page, /^Liquidity risk/);
  await expect(grid(page).getByRole('row', { name: /CHTR/ })).toHaveCount(0);
  await expect
    .poll(() => mock.views.at(-1))
    .toEqual({
      id: 'vrp_scanner',
      name: null,
      view: {
        columns: [],
        narrow_columns: [],
        filters: 'decision:QUALIFIED,WATCH,EVENT_RISK,PAUSED',
        sort: null,
        decisions: [],
      },
    });
  await page.getByRole('button', { name: /^What changed/ }).click();
  await page
    .getByRole('list', { name: 'Since the previous run' })
    .getByRole('button', { name: /^New/ })
    .click();
  await page.keyboard.press('Escape');
  await expect(grid(page).getByRole('row', { name: /SOXS/ })).toHaveCount(0);
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  await expect
    .poll(() => mock.views.at(-1)?.view['filters'])
    .toBe('decision:QUALIFIED,WATCH,EVENT_RISK,PAUSED;change:new');
});

test('a link with filters opens the filtered run; an empty result says what to switch off', async ({
  page,
}) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner?f=decision:QUALIFIED;change:dropped');
  await expect(page.getByText('No results match all 2 filters')).toBeVisible();
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toHaveCount(0);
  await page.getByRole('button', { name: /^Switch off Since the previous run gives 3/ }).click();
  await expect(page).toHaveURL(/f=decision(%3A|:)QUALIFIED(%3B|;)(%21|!)change/);
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  await expect(grid(page).getByRole('row', { name: /XOM/ })).toHaveCount(0);
  await expectAccessible(page);
  await page.getByRole('button', { name: 'Clear all' }).click();
  await expect(page).not.toHaveURL(/f=/);
  await expect(grid(page).getByRole('row', { name: /XOM/ })).toBeVisible();
});

test('a view can be saved under a name, switched to and deleted', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  await toggleDecision(page, /^Liquidity risk/); // a change to the default view
  await page.getByRole('button', { name: 'Save view as…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Save view as' });
  await dialog.getByLabel('Name of the view').fill('VRP review');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect
    .poll(() => mock.views.at(-1))
    .toMatchObject({
      id: 'vrp_scanner',
      name: 'VRP review',
      view: { filters: 'decision:QUALIFIED,WATCH,EVENT_RISK,PAUSED' },
    });
  const views = page.getByRole('combobox', { name: 'View' });
  await expect(views).toHaveValue('VRP review');
  // What you change now is saved into that view, not the default one.
  await toggleDecision(page, /^Watch/);
  await expect.poll(() => mock.views.at(-1)).toMatchObject({ name: 'VRP review' });
  await views.selectOption({ label: 'Default view' });
  await expect(views).toHaveValue('');
  await views.selectOption({ label: 'VRP review' });
  await page.getByRole('button', { name: 'Delete view' }).click();
  await expect.poll(() => mock.removedViews).toEqual(['VRP review']);
  await expect(views).toHaveValue('');
});

test('sorting is saved too, and a ticker opens in Explore', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await grid(page)
    .getByRole('button', { name: /^Score/ })
    .click();
  await expect.poll(() => mock.views.at(-1)?.view['sort']).toBe('-score');
  await grid(page).getByRole('row', { name: /AAPL/ }).click();
  await grid(page).press('Enter'); // a click reviews the row; Enter opens it
  await expect(page).toHaveURL(/\/explore\?.*focus=AAPL/);
});

test('the row under review has its detail and chart beside the table, moved with j and k', async ({
  page,
}) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  const detail = page.getByRole('region', { name: 'AAPL', exact: true });
  await expect(detail).toBeVisible(); // the first row is under review from the start
  await expect(detail).toContainText('new since the previous run');
  await expect(detail).toContainText('Passed');
  await expect(page.getByRole('region', { name: /AAPL · price/ })).toBeVisible();
  await focusLoadedGrid(page);
  await page.keyboard.press('j'); // the focused grid starts on the first row; j moves on
  await expect(page.getByRole('region', { name: 'SOXS', exact: true })).toContainText('Near miss');
  await page.keyboard.press('k');
  await expect(page.getByRole('region', { name: 'AAPL', exact: true })).toBeVisible();
});

test('c adds to the compare set, x hides a row for now, Enter opens Explore', async ({ page }) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await focusLoadedGrid(page);
  await page.keyboard.press('c'); // AAPL
  await page.keyboard.press('j');
  await page.keyboard.press('c'); // SOXS
  await expect(page.getByRole('button', { name: 'Compare 2 in Explore' })).toBeVisible();
  await page.keyboard.press('x'); // hide SOXS
  await expect(grid(page).getByRole('row', { name: /SOXS/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '1 hidden · Show' })).toBeVisible();
  await page.getByRole('button', { name: '1 hidden · Show' }).click();
  await expect(grid(page).getByRole('row', { name: /SOXS/ })).toBeVisible();
  await page.getByRole('button', { name: 'Compare 2 in Explore' }).click();
  await expect(page).toHaveURL(/\/explore\?.*sel=AAPL%2CSOXS/);
});

test('Enter on the row under review opens it in Explore', async ({ page }) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await focusLoadedGrid(page);
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/explore\?.*focus=AAPL/);
});

test('a screener with no run says so, and Run now runs it and shows the results', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp');
  await expect(
    page.getByText(
      'No run stored for this screener on 2026-10-02. Run it now to see what it picks.',
    ),
  ).toBeVisible();
  await expect(page.getByRole('group', { name: 'Last 1 sessions' })).toBeVisible();
  await expect(page.getByText('not run for this session')).toBeVisible(); // the reason, in public words
  await page.getByRole('button', { name: 'Run now' }).first().click(); // the run line's, above the table
  await expect(page.getByText('Running for 2026-10-02…')).toBeVisible();
  await expect(page.getByText('Run 2026-10-02', { exact: true })).toBeVisible(); // the line now says the run
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  expect(mock.runs).toEqual(['my-vrp']);
});

test('the run line says the last run and the strip shows the ten sessions with a label each', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await expect(page.getByText('Run 2026-10-02', { exact: true })).toBeVisible();
  await expect(
    page.getByText('v3 · 13 picked · +2 new, −1 dropped · Missing data for 8% of names'),
  ).toBeVisible();
  const strip = page.getByRole('group', { name: 'Last 10 sessions' });
  await expect(strip.getByRole('button')).toHaveCount(10);
  await expect(strip.getByRole('button', { name: 'Sep 24: Not run' })).toBeVisible();
  await expect(strip.getByRole('button', { name: 'Sep 29: Partial, 10 picked' })).toBeVisible();
  await expectAccessible(page);
  await strip.getByRole('button', { name: 'Sep 24: Not run' }).focus();
  await expect(page.getByText('Sep 24: Not run', { exact: true })).toBeVisible(); // the caption
  // A session that ran has no Run now beside the line (the table's own button stays).
  await expect(page.getByRole('button', { name: 'Run now' })).toHaveCount(1);
  expect(errors).toEqual([]);
});

test('Edit criteria opens the Builder; an edit there shows who would enter or leave', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await page.getByRole('button', { name: 'Edit criteria' }).click();
  await expect(page).toHaveURL(/\/screeners\/vrp_scanner\/edit$/);
  await expect(page.getByRole('dialog')).toHaveCount(0); // no drawer on the way
  const threshold = page.getByRole('spinbutton', { name: 'Threshold' }).first();
  await threshold.fill('60');
  await threshold.press('Enter');
  await expect.poll(() => mock.copies).toEqual([{ id: 'vrp_scanner', preset: 'vrp_scanner' }]);
  await expect(page.getByText('+3 enter: KO, MSFT, XOM.')).toBeVisible();
  await expect(page.getByText('-4 leave: CHTR, RKT, SOXS, UVXY.')).toBeVisible();
});

test('the page says which edge the screener implements, why each pick matched and what it counts toward', async ({
  page,
}) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  // Fix for: the results page showed nothing about edges. The headline edge is the strongest by status.
  const line = page.getByText('Earnings drift').first();
  await expect(line).toBeVisible();
  await expect(page.getByText('+1 edge')).toBeVisible();
  await expect(page.getByText('58.0%').first()).toBeVisible();
  await expect(page.getByText('51.0%').first()).toBeVisible();
  await page.getByRole('button', { name: 'Evidence' }).click();
  await expect(page.getByRole('button', { name: 'Momentum 12-1' })).toBeVisible();
  // The hits table: the rules a pick passed with their values, and what it counts toward.
  await expect(grid(page).getByRole('columnheader', { name: /Why it matched/ })).toBeVisible();
  const aapl = grid(page).getByRole('row', { name: /AAPL/ });
  await expect(aapl).toContainText('61.0%');
  await expect(aapl).toContainText('Counts');
  await expect(grid(page).getByRole('row', { name: /UVXY/ })).toContainText('Not counted');
  // A pick the regime gate held back is shown as not counted.
  await expect(grid(page).getByRole('row', { name: /XOM/ })).toContainText('Held back');
  // The pick's detail lists what it counts toward.
  await aapl.click();
  await expect(page.getByRole('heading', { level: 3, name: 'Counts toward' })).toBeVisible();
  await expectAccessible(page);
});

test('a screener no edge lists says so', async ({ page }) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/short-premium-liquidity');
  await expect(page.getByText(/Not part of an edge/)).toBeVisible();
});
