/**
 * Trader > Screeners > one screener (Results) end to end, against the production build with
 * the API mocked from fixtures shaped like GET /screens/{id}/table (builder-api.ts): the latest
 * run as a review table (criterion columns in their units, a tinted near miss, new / dropped
 * chips), decision filters and the user's view saved as they change it, the way to the Builder,
 * and the empty state of a screener with no run. Accessibility in both themes.
 */
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

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

async function expectAccessible(page: Page): Promise<void> {
  const axe = await new AxeBuilder({ page }).analyze();
  expect(axe.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
}

const grid = (page: Page) => page.getByRole('grid', { name: 'Screener results' });

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
    await expect(dkng).toContainText('new');
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

test('decision chips filter the run and the view is saved as yours', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  expect(mock.tables.at(-1)?.['decision']).toBe('QUALIFIED,WATCH,LIQUIDITY_RISK,EVENT_RISK');
  await page.getByRole('button', { name: /^Liquidity risk/ }).click();
  await expect
    .poll(() => mock.views.at(-1))
    .toEqual({
      id: 'vrp_scanner',
      name: null,
      view: { columns: [], sort: null, decisions: ['QUALIFIED', 'WATCH', 'EVENT_RISK'] },
    });
  await expect.poll(() => mock.tables.at(-1)?.['decision']).toBe('QUALIFIED,WATCH,EVENT_RISK');
  await page.getByRole('button', { name: /^New/ }).click();
  await expect.poll(() => mock.tables.at(-1)?.['change']).toBe('new');
});

test('a view can be saved under a name, switched to and deleted', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  await page.getByRole('button', { name: /^Liquidity risk/ }).click(); // a change to the default view
  await page.getByRole('button', { name: 'Save view as…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Save view as' });
  await dialog.getByLabel('Name of the view').fill('VRP review');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect
    .poll(() => mock.views.at(-1))
    .toMatchObject({
      id: 'vrp_scanner',
      name: 'VRP review',
      view: { decisions: ['QUALIFIED', 'WATCH', 'EVENT_RISK'] },
    });
  const views = page.getByRole('combobox', { name: 'View' });
  await expect(views).toHaveValue('VRP review');
  // What you change now is saved into that view, not the default one.
  await page.getByRole('button', { name: /^Watch/ }).click();
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
  await grid(page).focus();
  await page.keyboard.press('j'); // the focused grid starts on the first row; j moves on
  await expect(page.getByRole('region', { name: 'SOXS', exact: true })).toContainText('Near miss');
  await page.keyboard.press('k');
  await expect(page.getByRole('region', { name: 'AAPL', exact: true })).toBeVisible();
});

test('c adds to the compare set, x hides a row for now, Enter opens Explore', async ({ page }) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await grid(page).focus();
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
  await grid(page).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/explore\?.*focus=AAPL/);
});

test('a screener with no run says so, and Run now runs it and shows the results', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp');
  await expect(
    page.getByText('No run stored for this screener yet. Run it now to see what it picks.'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Run now' }).click();
  await expect(page.getByText('Running for 2026-10-02…')).toBeVisible();
  await expect(page.getByText('Updated for 2026-10-02')).toBeVisible();
  await expect(grid(page).getByRole('row', { name: /AAPL/ })).toBeVisible();
  expect(mock.runs).toEqual(['my-vrp']);
});

test('Edit criteria opens a drawer; an edit shows who would enter or leave, before saving', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await expect(page.getByText(/Unsaved changes/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit criteria' }).click();
  const drawer = page.getByRole('dialog', { name: 'vrp_scanner · criteria' });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole('heading', { level: 1 })).toHaveCount(0); // no second page heading
  const threshold = drawer.getByRole('spinbutton', { name: 'Threshold' }).first();
  await threshold.fill('60');
  await threshold.press('Enter');
  await expect.poll(() => mock.copies).toEqual([{ id: 'vrp_scanner', preset: 'vrp_scanner' }]);
  await expect(drawer.getByText('+3 enter: KO, MSFT, XOM.')).toBeVisible();
  await expect(drawer.getByText('-4 leave: CHTR, RKT, SOXS, UVXY.')).toBeVisible();
  await expect(drawer.getByText('DRAFT v1 · unsaved changes')).toBeVisible();
  // Closing the drawer leaves the note above the results while the edit is unsaved.
  await drawer.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.getByText('+3 enter: KO, MSFT, XOM.')).toBeVisible();
  await page.getByRole('button', { name: 'Review criteria' }).click();
  await expect(drawer).toBeVisible();
});

test('the full Builder is one click away from the drawer', async ({ page }) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp');
  await page.getByRole('button', { name: 'Edit criteria' }).click();
  await page.getByRole('button', { name: 'Open in Builder' }).click();
  await expect(page).toHaveURL(/\/screeners\/my-vrp\/edit$/);
});
