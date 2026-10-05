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
    const dkng = grid(page).getByRole('row', { name: /DKNG/ });
    await expect(dkng).toContainText('DraftKings Inc.');
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
  await expect(grid(page).getByRole('row', { name: /DKNG/ })).toBeVisible();
  expect(mock.tables.at(-1)?.['decision']).toBe('QUALIFIED,WATCH,LIQUIDITY_RISK,EVENT_RISK');
  await page.getByRole('button', { name: /^Liquidity risk/ }).click();
  await expect
    .poll(() => mock.views.at(-1))
    .toEqual({
      id: 'vrp_scanner',
      view: { columns: [], sort: null, decisions: ['QUALIFIED', 'WATCH', 'EVENT_RISK'] },
    });
  await expect.poll(() => mock.tables.at(-1)?.['decision']).toBe('QUALIFIED,WATCH,EVENT_RISK');
  await page.getByRole('button', { name: /^New/ }).click();
  await expect.poll(() => mock.tables.at(-1)?.['change']).toBe('new');
});

test('sorting is saved too, and a ticker opens in Explore', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner');
  await grid(page)
    .getByRole('button', { name: /^Score/ })
    .click();
  await expect.poll(() => mock.views.at(-1)?.view['sort']).toBe('-score');
  await grid(page).getByRole('row', { name: /DKNG/ }).click();
  await expect(page).toHaveURL(/\/explore\?.*focus=DKNG/);
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
  await expect(grid(page).getByRole('row', { name: /DKNG/ })).toBeVisible();
  expect(mock.runs).toEqual(['my-vrp']);
});

test('the Builder is one click away', async ({ page }) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp');
  await page.getByRole('button', { name: 'Edit criteria' }).click();
  await expect(page).toHaveURL(/\/screeners\/my-vrp\/edit$/);
});
