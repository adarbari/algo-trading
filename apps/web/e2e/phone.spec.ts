/**
 * The app on a phone (iPhone 13: touch, 390 px wide; the `phone` project of playwright.config.ts,
 * ADR 0025 rule 10), against the production build with the API mocked: every top-bar route fits
 * the screen (no horizontal page scroll, a top bar that does not eat it), logs no errors and is
 * accessible; a ticker opens its detail as a sheet; a screener name opens its results; the chart
 * has zoom buttons for fingers; the ingestion drill-down opens as a sheet; a tooltip opens on
 * a tap; the keyboard hints are gone; a narrow table shows its essential columns with the picker; a Regime card's help opens as a sheet.
 */
import { expect, test, type Page } from '@playwright/test';

import { WORKSPACES } from '../src/app/workspaces/workspaces';
import { expectAccessible, settled } from './a11y';
import { mockAdminApi } from './admin-api';
import { mockViewer } from './auth-api';
import { mockApi } from './mock-api';

/** Every section, and the Guide (its own layout, outside the workspaces) with its regime pages. */
const ROUTES = [
  ...WORKSPACES.flatMap((w) => w.sections.map((s) => s.path)),
  '/guide',
  '/guide/start/how_the_app_thinks',
  '/guide/glossary',
  '/guide/regime',
  '/guide/regime/indicators/curve_10y3m',
  '/guide/regime/episodes/gfc_2007',
];
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
  // A long name: the account menu must truncate it, not overflow the top bar.
  await mockViewer(page, { name: 'Alexandra Montgomery-Fitzwilliam' });
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

test('Regime: a tapped card help button opens the indicator drawer as a sheet', async ({
  page,
}) => {
  await page.goto('/regime');
  const card = page.getByRole('region', { name: 'Slow-moving warning signs' });
  await card
    .getByRole('button', { name: /^What is / })
    .first()
    .tap();
  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('heading', { level: 3, name: 'Why it matters' })).toBeVisible();
  await expectAccessible(page);
});

test('Screeners: a tapped row opens in place and its hits button opens the results', async ({
  page,
}) => {
  await page.goto('/screeners');
  const row = page.getByRole('button', { name: /^vrp_scanner Preset/ });
  // On a phone the row keeps the name, the type pill and the hits only.
  await expect(row.getByText('Run 2026-10-07')).toBeHidden();
  await row.tap();
  await expect(row).toHaveAttribute('aria-expanded', 'true');
  await expectAccessible(page);
  await page.getByRole('button', { name: 'View 12 hits' }).tap();
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

test('Explore: the filter bar is one "Filters" button that opens a sheet with the quick chips', async ({
  page,
}) => {
  await page.goto('/explore');
  const bar = page.getByRole('group', { name: 'Filters' });
  await expect(bar.getByRole('searchbox', { name: 'Filter tickers' })).toBeVisible();
  await expect(bar.getByRole('button', { name: 'Optionable' })).toHaveCount(0);
  await bar.getByRole('button', { name: /^Filters/ }).tap();
  const sheet = page.getByRole('dialog', { name: 'Filters' });
  await expect(sheet.getByRole('button', { name: 'Optionable' })).toBeVisible();
});

test('Screener results: the pick actions are icon buttons named by their label', async ({
  page,
}) => {
  await page.goto('/screeners/vrp_scanner');
  await page.getByRole('grid').first().getByRole('row', { name: /AAPL/ }).tap();
  const sheet = page.getByRole('dialog', { name: 'AAPL' });
  const open = sheet.getByRole('button', { name: 'Open in Explore' });
  await expect(open).toBeVisible();
  await expect(open).toHaveText('');
  await expect(open).toHaveAccessibleDescription('Open in Explore');
});

test('Explore: a column added on the phone is kept in the URL (ncols)', async ({ page }) => {
  await page.goto('/explore');
  await page.getByRole('button', { name: /Columns \d+ of \d+/ }).tap();
  const panel = page.getByRole('group', { name: 'Show columns' });
  const unchecked = panel.getByRole('checkbox', { checked: false }).first();
  await unchecked.check();
  await expect(page).toHaveURL(/ncols=/);
});

test('Explore: the catalogue and narrow-table Columns buttons share one row', async ({ page }) => {
  await page.goto('/explore');
  const buttons = page.getByRole('button', { name: /^Columns/ });
  await expect(buttons).toHaveCount(2);
  const [a, b] = await Promise.all([buttons.nth(0).boundingBox(), buttons.nth(1).boundingBox()]);
  expect(a?.y).toBeDefined();
  expect(a?.y).toBe(b?.y);
});

test('the top bar keeps every button on screen with a long viewer name', async ({ page }) => {
  await page.goto('/ideas');
  const buttons = page.getByRole('banner').getByRole('button');
  await expect(buttons.first()).toBeVisible();
  const innerWidth = await page.evaluate(() => window.innerWidth);
  for (const button of await buttons.all()) {
    const box = await button.boundingBox();
    // Hidden ones (a collapsed menu's items) have no box.
    if (box) expect(box.x + box.width).toBeLessThanOrEqual(innerWidth);
  }
});

test('Guide search: the rail button opens the dialog inside the viewport, a tapped result opens its page', async ({
  page,
}) => {
  await page.goto('/guide/glossary');
  await page.getByRole('button', { name: 'Search the Guide' }).tap();
  const dialog = page.getByRole('dialog', { name: 'Search the Guide' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('searchbox').fill('session');
  const result = dialog.getByRole('link', { name: /^Session/ });
  await expect(result).toBeVisible();
  const box = await dialog.boundingBox();
  const width = page.viewportSize()?.width ?? 0;
  expect((box?.x ?? -1) >= 0 && (box?.x ?? 0) + (box?.width ?? 0) <= width).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    width,
  );
  await expectAccessible(page);
  await result.tap();
  await expect(page).toHaveURL(/\/guide\/glossary\/session$/);
});

test('Edges: a tapped edge opens its detail as a sheet', async ({ page }) => {
  await page.goto('/edges');
  await page.getByRole('row', { name: /Momentum 12-1/ }).tap();
  const sheet = page.getByRole('dialog', { name: 'momentum_12_1' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText('58.0%').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    page.viewportSize()?.width ?? 0,
  );
});

test('Harness runs: a tapped run opens its rows as a sheet', async ({ page }) => {
  await mockAdminApi(page, {
    harnessRuns: [
      {
        runId: 'run-b',
        edgeId: 'momentum_12_1',
        user: 'site',
        status: 'complete',
        startedAt: '2026-10-05T02:00:00+00:00',
        finishedAt: null,
        rangeFrom: null,
        rangeTo: '2026-10-02',
        splitFrom: null,
        exploratory: false,
        variants: [],
        horizons: [],
        sessions: null,
        unclosed: null,
        excludedCoverage: null,
        scoreCoverage: null,
        noEntryBar: null,
        trials: null,
        knowledgeTs: '2026-10-05T02:00:00+00:00',
        asOf: null,
      },
    ],
    'harnessRun:run-b': { runId: 'run-b', rows: [], lostInputs: [] },
  });
  await page.goto('/admin/harness-runs');
  // A phone shows 3 of the columns (edge, started, status): the run id is in the sheet
  await page.getByRole('row', { name: /momentum_12_1/ }).tap();
  await expect(page.getByRole('dialog', { name: 'run-b' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    page.viewportSize()?.width ?? 0,
  );
});
