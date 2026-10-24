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
import FORMULAS from './fixtures/accepted-formulas.json' with { type: 'json' };
import REQUESTS from './fixtures/feature-requests.json' with { type: 'json' };
import { mockBuilderApi, mockDescribeApi } from './builder-api';
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
  '/guide/edges',
  '/guide/edges/m/slow_to_update',
  '/guide/edges/earnings_date_advance',
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

test('Explore: the search adds a ticker as a tab and the tab strip stays on the screen', async ({
  page,
}) => {
  await page.goto('/explore?sel=AAPL,MSFT');
  const box = page.getByRole('combobox', { name: 'Search tickers' });
  await box.fill('nvda');
  await page.getByRole('option').first().tap();
  const tabs = page.getByRole('tablist', { name: 'Open tickers' });
  await expect(tabs.getByRole('tab')).toHaveText(['AAPL', 'MSFT', 'NVDA']);
  await expect(tabs.getByRole('tab', { name: 'NVDA' })).toHaveAttribute('aria-selected', 'true');
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
  await tabs.getByRole('tab', { name: 'MSFT' }).tap();
  await expect(page).toHaveURL(/focus=MSFT/);
});

test('Ideas: the filter bar is one Filters button and a sheet, "Show N results" narrows the table, and an empty result offers the way back', async ({
  page,
}) => {
  await page.goto('/ideas');
  const innerWidth = await page.evaluate(() => window.innerWidth);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    innerWidth,
  );
  await expect(page.getByRole('button', { name: 'Setup' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Filters' }).tap();
  const sheet = page.getByRole('dialog', { name: 'Filters' });
  await sheet.getByRole('button', { name: 'Setup' }).tap();
  await page
    .getByRole('list', { name: 'Decision' })
    .getByRole('button', { name: /^Event risk/ })
    .tap();
  await page.keyboard.press('Escape');
  await expect(sheet.getByRole('button', { name: 'Show 1 results' })).toBeVisible();
  await sheet.getByRole('button', { name: 'Show 1 results' }).tap();
  await expect(page).toHaveURL(/f=decision(%3A|:)EVENT_RISK/);
  await expect(
    page.getByRole('grid', { name: 'Top ideas' }).getByRole('row', { name: /TSLA/ }),
  ).toBeVisible();
  const chips = page.getByRole('group', { name: 'Applied filters' });
  const box = await chips.boundingBox();
  expect(box && box.x + box.width).toBeLessThanOrEqual(innerWidth);
  await page.goto('/ideas?f=decision:EVENT_RISK;agreeing:3..');
  await expect(page.getByText('No ideas match all 2 filters')).toBeVisible();
  await page.getByRole('button', { name: /^Switch off Agreeing screeners gives 1/ }).tap();
  await expect(
    page.getByRole('grid', { name: 'Top ideas' }).getByRole('row', { name: /TSLA/ }),
  ).toBeVisible();
});

test('Ideas: the screener chips wrap inside the screen and a tapped one opens the screener', async ({
  page,
}) => {
  await page.goto('/ideas');
  const innerWidth = await page.evaluate(() => window.innerWidth);
  const items = page.getByRole('list', { name: 'Screeners' }).getByRole('listitem');
  await expect(items).toHaveCount(4);
  for (const item of await items.all()) {
    const box = await item.boundingBox();
    expect(box && box.x + box.width).toBeLessThanOrEqual(innerWidth);
  }
  await items.first().getByRole('link').tap();
  await expect(page).toHaveURL(/\/screeners\/vrp-scanner/);
});

test('Ideas: a phone row keeps the ticker, who picked it, decision and score', async ({ page }) => {
  await page.goto('/ideas');
  const headers = page.getByRole('grid', { name: 'Top ideas' }).getByRole('columnheader');
  await expect(headers).toContainText(['Ticker', 'Picked by', 'Decision', 'Score']);
  await expect(headers.filter({ hasText: /Price|Watch out/ })).toHaveCount(0);
});

test('Explore chart: the zoom buttons are there', async ({ page }) => {
  await page.goto('/explore?focus=AAPL&tab=chart');
  await expect(page.getByRole('button', { name: 'Zoom in' })).toBeVisible();
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

test('Screener results: the pick opens as a full-height sheet; next, previous and back work', async ({
  page,
}) => {
  await page.goto('/screeners/vrp_scanner');
  const picks = page.getByRole('grid').first();
  await picks.getByRole('row', { name: /AAPL/ }).tap();
  const sheet = page.getByRole('dialog', { name: 'AAPL' });
  await expect(sheet).toBeVisible();
  const viewport = page.viewportSize();
  const box = await sheet.boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual((viewport?.height ?? 0) - 1);
  await expect(sheet.getByRole('button', { name: 'Previous' })).toBeDisabled();
  await sheet.getByRole('button', { name: 'Next' }).tap();
  await expect(page.getByRole('dialog', { name: 'AAPL' })).toHaveCount(0);
  const next = page.getByRole('dialog');
  await expect(next).toBeVisible();
  await next.getByRole('button', { name: 'Previous' }).tap();
  await expect(page.getByRole('dialog', { name: 'AAPL' })).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Back to list' }).tap();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(picks.getByRole('row', { name: /AAPL/ })).toBeVisible();
});

test('Regime: a tapped card help button opens the indicator drawer as a sheet', async ({
  page,
}) => {
  await page.goto('/regime');
  const card = page.getByRole('region', { name: 'Slow-moving warning signs' });
  await card.getByRole('listitem').first().getByRole('button').first().tap();
  await card
    .getByRole('button', { name: /^What is / })
    .first()
    .tap();
  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('heading', { level: 3, name: 'Why it matters' })).toBeVisible();
  await expectAccessible(page);
});

test('Screeners: each row is a card with evidence, picks and labelled actions, and no header', async ({
  page,
}) => {
  await page.goto('/screeners');
  const row = page.getByRole('row').filter({ hasText: 'vrp_scanner' });
  // On a phone the table is a list of cards: the header row is gone, every cell stays.
  await expect(page.getByRole('columnheader', { name: 'Evidence and edges' })).toBeHidden();
  await expect(row.getByRole('button', { name: /: 12 picks$/ })).toBeVisible();
  await expect(row.getByRole('button', { name: 'Duplicate to edit' })).toBeVisible();
  // The card holds no sideways scroll.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await expectAccessible(page);
  await row.getByRole('button', { name: /: 12 picks$/ }).tap();
  await expect(page).toHaveURL(/\/screeners\/vrp_scanner$/);
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

test('Guide Edges: a tapped card opens its mechanism, a tapped edge its page, then the live evidence', async ({
  page,
}) => {
  await page.goto('/guide/edges');
  await page.getByRole('link', { name: 'Slow to update', exact: true }).first().tap();
  await expect(page).toHaveURL(/\/guide\/edges\/m\/slow_to_update$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Slow to update' })).toBeVisible();
  await page
    .getByRole('region', { name: 'The edges in this mechanism' })
    .getByRole('link', { name: 'Earnings-date advances' })
    .tap();
  await expect(page).toHaveURL(/\/guide\/edges\/earnings_date_advance$/);
  const evidence = page.getByRole('button', { name: 'See the live evidence' });
  await expect(evidence).toBeVisible();
  const innerWidth = await page.evaluate(() => window.innerWidth);
  const box = await evidence.boundingBox();
  expect(box && box.x + box.width).toBeLessThanOrEqual(innerWidth);
  await evidence.tap();
  await expect(page).toHaveURL(/\/edges\?edge=earnings_date_advance$/);
});

test('Edges: a tapped edge opens its page', async ({ page }) => {
  await page.goto('/edges');
  await page.getByRole('row', { name: /Momentum 12-1/ }).tap();
  await expect(page.getByRole('heading', { level: 1, name: 'Momentum 12-1' })).toBeVisible();
  // The evaluation line wraps inside the screen like the rest of the head.
  await expect(page.getByText(/^Evaluated 2 Oct, 8 sessions ago\./)).toBeInViewport();
  await expect(page.getByRole('button', { name: 'Run backtest' })).toBeVisible();
  await page.mouse.wheel(0, 400); // the sections load as they are reached
  await expect(page.getByText('+7.0 pts').first()).toBeVisible();
  const fits = async () => {
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      page.viewportSize()?.width ?? 0,
    );
  };
  await fits();
  // The sections stack in one column and none widens the page: the curve, the three cards of
  // How sure, the years and the drawdown view.
  await expect(page.getByRole('img', { name: /^Evidence curve of the picks/ })).toBeVisible();
  await fits();
  await page
    .getByRole('navigation', { name: 'Sections of this edge' })
    .getByRole('link', { name: 'How sure' })
    .tap();
  await expect(page.getByRole('list', { name: 'Decay by stage' })).toBeVisible();
  await fits();
  await page
    .getByRole('navigation', { name: 'Sections of this edge' })
    .getByRole('link', { name: 'Where it worked' })
    .tap();
  await page.getByRole('tab', { name: 'Drawdown' }).tap();
  await expect(page.getByRole('grid', { name: 'Deepest drawdowns' })).toBeVisible();
  await fits();
  await page.getByRole('tab', { name: 'Holding period' }).tap();
  await expect(page.getByRole('grid', { name: 'By holding period' })).toBeVisible();
  await fits();
  await page
    .getByRole('navigation', { name: 'Sections of this edge' })
    .getByRole('link', { name: 'Trades' })
    .tap();
  await expect(page.getByRole('grid', { name: 'Trade ledger' })).toBeVisible();
  await fits(); // the ledger scrolls sideways inside its own box, never the page
  await expectAccessible(page);
});

test('Edge builder: the six steps fit a phone, the steps scroll sideways and a step opens from the nav', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/edges/new');
  const nav = page.getByRole('navigation', { name: 'Edge builder steps' });
  await expect(nav.getByRole('link', { name: '4 · Trade' })).toBeAttached();
  await nav.getByRole('link', { name: '4 · Trade' }).tap();
  await expect(page.getByRole('heading', { name: '4 · Trade' })).toBeInViewport();
  const width = page.viewportSize()?.width ?? 0;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    width,
  );
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('Builder: a condition group is one column that fits the screen (ADR 0071)', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp/edit');
  await page.getByRole('button', { name: 'Either this or the previous' }).first().tap();
  const group = page.getByRole('region', { name: /or/ }).filter({ hasText: 'Any of' });
  await expect(group).toBeVisible();
  const width = page.viewportSize()?.width ?? 0;
  const box = await group.boundingBox();
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    width,
  );
  await expect(group.getByRole('button', { name: 'Ungroup' })).toBeInViewport();
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('Describe it: the review fits the screen and the formula dialog fills it', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await mockBuilderApi(page);
  await mockDescribeApi(page);
  await page.goto('/screeners/my-vrp/edit');
  await page.getByRole('textbox', { name: 'Describe the screen' }).fill('IV above HV');
  await page.getByRole('button', { name: 'Draft it' }).tap();
  await expect(page.getByRole('article', { name: 'IV above HV' })).toBeVisible();
  const width = page.viewportSize()?.width ?? 0;
  const pageWidth = () => page.evaluate(() => document.documentElement.scrollWidth);
  expect(await pageWidth()).toBeLessThanOrEqual(width);
  for (const card of await page.getByRole('article').all()) {
    const cardBox = await card.boundingBox();
    expect((cardBox?.x ?? 0) + (cardBox?.width ?? 0)).toBeLessThanOrEqual(width);
  }
  const pending = page.getByRole('group', { name: /Waiting on formula/ });
  await expect(pending).toBeVisible();
  const row = await pending.boundingBox();
  expect((row?.x ?? 0) + (row?.width ?? 0)).toBeLessThanOrEqual(width);
  await expectAccessible(page);
  // Retype opens in the card and fits the screen, Redraft and Cancel in reach
  const card = page.getByRole('article', { name: 'and above 50%' });
  await card.getByRole('button', { name: 'Retype this part' }).tap();
  await expect(card.getByRole('textbox', { name: 'Retype this part' })).toBeVisible();
  await expect(card.getByRole('button', { name: 'Redraft' })).toBeInViewport();
  await expect(card.getByRole('button', { name: 'Cancel' })).toBeInViewport();
  expect(await pageWidth()).toBeLessThanOrEqual(width);
  await expectAccessible(page);
  await card.getByRole('button', { name: 'Cancel' }).tap();
  await expect(card.getByRole('button', { name: 'Retype this part' })).toBeFocused();
  await page.getByRole('button', { name: 'Review and add' }).first().tap();
  const dialog = page.getByRole('dialog', { name: 'Add formula feature' });
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  const height = page.viewportSize()?.height ?? 0;
  expect(box?.x ?? 1).toBeLessThanOrEqual(1);
  expect(box?.width ?? 0).toBeGreaterThanOrEqual(width - 1);
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(height - 1);
  await expect(dialog.getByRole('button', { name: 'Save feature' })).toBeInViewport();
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('Edge runs: a tapped run opens its rows as a sheet', async ({ page }) => {
  await mockAdminApi(page, {
    harnessRuns: [
      {
        runId: 'run-b',
        edgeId: 'momentum_12_1',
        user: 'site',
        status: 'COMPLETE',
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

test('Screener runs: a tapped run opens its record as a sheet', async ({ page }) => {
  await mockAdminApi(page, {
    screenerRuns: [
      {
        runId: 'screen-trend-site',
        configId: 'trend_pullback',
        owner: 'site',
        session: '2026-10-22',
        status: 'COMPLETE',
        startedAt: '2026-10-22T22:05:00+00:00',
        finishedAt: null,
        knowledgeTs: '2026-10-22T22:05:00+00:00',
        picked: null,
        paused: null,
        regime: null,
        coverage: null,
      },
    ],
    'screenerRun:screen-trend-site': {
      runId: 'screen-trend-site',
      configId: 'trend_pullback',
      owner: 'site',
      session: '2026-10-22',
      status: 'COMPLETE',
      startedAt: '2026-10-22T22:05:00+00:00',
      finishedAt: null,
      knowledgeTs: '2026-10-22T22:05:00+00:00',
      configVersion: null,
      configHash: null,
      decisions: null,
      picked: null,
      paused: null,
      regime: null,
      coverage: null,
      missingTables: [],
      missingOptionalTables: [],
      unavailable: [],
      changes: null,
    },
  });
  await page.goto('/admin/screener-runs');
  await page.getByRole('row', { name: /trend_pullback/ }).tap();
  await expect(page.getByRole('dialog', { name: 'screen-trend-site' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    page.viewportSize()?.width ?? 0,
  );
});

test('Feature requests: the ranked list and the accepted formulas fit a phone and a status filter narrows it', async ({
  page,
}) => {
  await mockAdminApi(page, { featureRequests: REQUESTS, acceptedFormulas: FORMULAS });
  await page.goto('/admin/feature-requests');
  await expect(page.getByRole('row', { name: /realised_vol_20d/ })).toBeVisible();
  await page.getByRole('radio', { name: 'Promoted' }).tap();
  await expect(page).toHaveURL(/status=PROMOTED/);
  await expect(page.getByRole('table', { name: 'Accepted formulas' })).toContainText(
    'close/sma_20 - 1',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    page.viewportSize()?.width ?? 0,
  );
});

test('Screener results: the edge line and the evidence fit a phone and the pick sheet lists what it counts toward', async ({
  page,
}) => {
  await page.goto('/screeners/vrp_scanner');
  await expect(page.getByText('Earnings drift').first()).toBeVisible();
  await page.getByRole('button', { name: 'Evidence' }).tap();
  await expect(page.getByRole('button', { name: 'Momentum 12-1' })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);
  await page.getByRole('grid').first().getByRole('row', { name: /AAPL/ }).tap();
  const sheet = page.getByRole('dialog', { name: 'AAPL' });
  await expect(sheet.getByRole('heading', { level: 3, name: 'Counts toward' })).toBeVisible();
  await expectAccessible(page);
});

/** The strip's read with the pill's state, and the popover's detail read (the pill's states). */
async function mockDataStatus(page: Page, state: string, newer: string | null) {
  await page.route('**/api/graphql', async (route) => {
    const query = (route.request().postDataJSON() as { query?: string } | null)?.query ?? '';
    const session = {
      date: '2026-10-22',
      newer: newer === null ? null : { date: newer, state: 'IN_PROGRESS' },
    };
    if (/query\s+StatusStrip\b/.test(query)) {
      await route.fulfill({
        json: { data: { session: { ...session, dataStatus: { state } }, screeners: [] } },
      });
      return;
    }
    if (!/query\s+DataStatus\b/.test(query)) {
      await route.fallback();
      return;
    }
    const dataset = (name: string, status: string, share: number) => ({
      name,
      status,
      share,
      unavailable: [],
    });
    await route.fulfill({
      json: {
        data: {
          session: {
            ...session,
            dataStatus: {
              state,
              knowledgeTs: '2026-10-22T21:05:00+00:00',
              datasets: [
                dataset('PRICES', 'COMPLETE', 0.99),
                dataset('OPTIONS_CHAINS', 'PARTIAL', 0.62),
                dataset('FUNDAMENTALS', 'COMPLETE', 0.9),
              ],
              affectedScreeners: 2,
              totalScreeners: 7,
            },
          },
        },
      },
    });
  });
}

const PILL_STATES = [
  ['COMPLETE', null, 'Data: 22 Oct, complete', 'Data: complete'],
  ['PARTIAL', null, 'Data: 22 Oct, partial', 'Data: partial'],
  ['NEXT_PROCESSING', '2026-10-23', '23 Oct is processing', 'Processing'],
  ['NEXT_FAILED_SHOWING_PREVIOUS', '2026-10-23', '23 Oct failed, showing 22 Oct', 'Failed'],
] as const;

for (const [state, newer, full, short] of PILL_STATES) {
  test(`Data-status pill ${state}: the phone shows "${short}" and the full wording names it`, async ({
    page,
  }) => {
    await mockDataStatus(page, state, newer);
    await page.goto('/ideas');
    const pill = page.getByRole('button', { name: full });
    await expect(pill).toBeVisible();
    await expect(pill.getByText(short, { exact: true })).toBeVisible();
    await expect(pill.getByText(full, { exact: true })).toBeHidden();
    const { scrollWidth, innerWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
  });
}

test('Data-status pill: a tap opens the datasets inside the phone screen', async ({ page }) => {
  await mockDataStatus(page, 'PARTIAL', null);
  await page.goto('/ideas');
  await page.getByRole('button', { name: 'Data: 22 Oct, partial' }).tap();
  const panel = page.getByRole('dialog', { name: 'Data status' });
  for (const name of ['Prices', 'Options chains', 'Fundamentals'])
    await expect(panel.getByText(name, { exact: true })).toBeVisible();
  await expect(panel.getByText('62% of names')).toBeVisible();
  await expect(panel.getByText('Affects 2 of your 7 screeners')).toBeVisible();
  const box = await panel.boundingBox();
  const width = page.viewportSize()?.width ?? 0;
  expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(width);
});
