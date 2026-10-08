/**
 * The app on a phone (iPhone 13: touch, 390 px wide; the `phone` project of playwright.config.ts,
 * ADR 0025 rule 10), against the production build with the API mocked: every top-bar route fits
 * the screen (no horizontal page scroll, a top bar that does not eat it), logs no errors and is
 * accessible; a ticker opens its detail as a sheet; a screener name opens its results; the chart
 * has zoom buttons for fingers; the ingestion drill-down opens as a sheet; a tooltip opens on
 * a tap; the keyboard hints are gone; a narrow table shows its essential columns with the picker.
 */
import { expect, test, type Page } from '@playwright/test';

import { WORKSPACES } from '../src/app/workspaces/workspaces';
import { expectAccessible, settled } from './a11y';
import { mockApi } from './mock-api';

/** Every section, and the Guide (its own layout, outside the workspaces). */
const ROUTES = [...WORKSPACES.flatMap((w) => w.sections.map((s) => s.path)), '/guide'];
/**
 * The top bar's height bound: the two-row grid under 720 px (brand, Guide and the end slot,
 * then the nav; the workspace switch is in the account menu) measures about 100 px at 390 px.
 */
const TOP_BAR_MAX_PX = 112;

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

for (const route of ROUTES) {
  test(`${route} fits a phone`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto(route);
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
    await settled(page);
    const { scrollWidth, innerWidth, innerHeight } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
    const bar = await page.getByRole('banner').boundingBox();
    expect(bar?.height ?? 0).toBeGreaterThan(0);
    expect(bar?.height ?? 0).toBeLessThanOrEqual(TOP_BAR_MAX_PX);
    expect(bar?.height ?? 0).toBeLessThan(innerHeight * 0.3);
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('Explore: a tapped ticker opens its detail in a sheet, closing it shows the table', async ({
  page,
}) => {
  await page.goto('/explore');
  const tickers = page.getByRole('grid', { name: 'Tickers' });
  // The table is virtualised and sorted by symbol: the first row is A (Agilent).
  await tickers.getByRole('gridcell', { name: /^A Agilent/ }).tap();
  const sheet = page.getByRole('dialog', { name: 'A', exact: true });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('tab').first()).toBeVisible();
  await sheet.getByRole('button', { name: /close/i }).first().tap();
  await expect(sheet).toHaveCount(0);
  await expect(tickers).toBeVisible();
});

test('Ideas: a screener name opens its results', async ({ page }) => {
  await page.goto('/ideas');
  const screeners = page.getByRole('list', { name: 'Screener priority' });
  await screeners.getByRole('button', { name: 'VRP scanner', exact: true }).tap();
  await expect(page).toHaveURL(/\/screeners\/[^/]+$/);
});

test('Explore chart: the zoom buttons are there', async ({ page }) => {
  await page.goto('/explore?focus=AAPL&tab=chart');
  const sheet = page.getByRole('dialog', { name: 'AAPL' });
  await expect(sheet.getByRole('button', { name: 'Zoom in' })).toBeVisible();
});

test('Admin ingestion: a tapped completeness cell opens its drill-down in a sheet', async ({
  page,
}) => {
  await page.goto('/admin/ingestion');
  const grid = page.getByRole('grid', { name: 'Completeness by dataset and session' });
  await grid
    .getByRole('gridcell', { name: /^Option chains, / })
    .last()
    .tap();
  const sheet = page.getByRole('dialog', { name: /^Option chains · \d{4}-\d{2}-\d{2}$/ });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText(/of .* expected/)).toBeVisible();
  await sheet.getByRole('button', { name: /close/i }).first().tap();
  await expect(sheet).toHaveCount(0);
  await expect(page).toHaveURL(/\/admin\/ingestion$/);
});

test('a tooltip opens on a tap', async ({ page }) => {
  await page.goto('/admin/ingestion');
  const trigger = page.getByRole('button', { name: 'Re-run nightly' });
  await trigger.scrollIntoViewIfNeeded();
  await trigger.tap({ force: true });
  await expect(page.getByRole('tooltip')).toContainText('Coming with the jobs API');
});

test('Screener results: the pick sheet shows no keyboard hints on a phone', async ({ page }) => {
  await page.goto('/screeners/vrp_scanner');
  const picks = page.getByRole('grid').first();
  await picks.getByRole('row', { name: /AAPL/ }).tap();
  const sheet = page.getByRole('dialog', { name: 'AAPL' });
  await expect(sheet.getByRole('button', { name: 'Open in Explore' })).toBeVisible();
  await expect(sheet.getByRole('list', { name: 'Keyboard shortcuts' })).toBeHidden();
});

test('Screeners: a tapped row opens the screener', async ({ page }) => {
  await page.goto('/screeners');
  const presets = page.getByRole('grid', { name: 'Site presets' });
  await presets.getByRole('gridcell', { name: 'vrp_scanner' }).first().tap();
  await expect(page).toHaveURL(/\/screeners\/vrp_scanner$/);
});

test('Explore: a narrow table shows its essential columns and the picker for the rest', async ({
  page,
}) => {
  await page.goto('/explore');
  const tickers = page.getByRole('grid', { name: 'Tickers' });
  await expect(tickers).toBeVisible();
  // The select-all checkbox, the ticker and the first two catalogue columns; the rest wait.
  await expect(tickers.getByRole('columnheader')).toHaveCount(4);
  await expect(page.getByRole('button', { name: /Columns \d+ of \d+/ })).toBeVisible();
});

test('Explore: ticked tickers open the compare detail from the Compare button', async ({
  page,
}) => {
  await page.goto('/explore?sel=AAPL,MSFT');
  await page.getByRole('button', { name: 'Compare 2' }).tap();
  await expect(page.getByRole('dialog', { name: 'AAPL' })).toBeVisible();
});
