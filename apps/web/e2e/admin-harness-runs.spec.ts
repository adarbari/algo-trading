/**
 * Admin > Harness runs end to end against a mocked API: the runs list with what each measured and
 * left out (an unrecorded figure stays empty, an exploratory split is labelled), a run's rows
 * beside it (the choice lives in the URL), accessible in dark and light; a failed read shows its
 * error.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { FAIL, mockAdminApi, mockNoGuideEntries } from './admin-api';
import { mockViewer } from './auth-api';
import { mockRegimeApi } from './regime-api';

const RUNS = [
  {
    runId: 'run-b',
    edgeId: 'momentum_12_1',
    user: 'site',
    status: 'complete',
    startedAt: '2026-10-05T02:00:00+00:00',
    finishedAt: '2026-10-05T02:10:00+00:00',
    rangeFrom: '2012-01-03',
    rangeTo: '2026-10-02',
    splitFrom: '2024-01-01',
    exploratory: false,
    variants: ['equal_weight', 'momentum_12_1'],
    horizons: [21],
    sessions: 120,
    unclosed: 3,
    excludedCoverage: 2,
    scoreCoverage: 0.92,
    noEntryBar: 7,
    trials: 4,
    knowledgeTs: '2026-10-05T02:10:00+00:00',
    asOf: '2026-10-04T00:00:00+00:00',
  },
  {
    runId: 'run-a',
    edgeId: 'momentum_12_1',
    user: 'abhi',
    status: 'failed',
    startedAt: '2026-10-04T02:00:00+00:00',
    finishedAt: null,
    rangeFrom: null,
    rangeTo: '2026-10-02',
    splitFrom: '2022-06-01',
    exploratory: true,
    variants: [],
    horizons: [],
    sessions: null,
    unclosed: null,
    excludedCoverage: null,
    scoreCoverage: null,
    noEntryBar: null,
    trials: null,
    knowledgeTs: '2026-10-04T02:00:00+00:00',
    asOf: null,
  },
];

const ROWS = {
  runId: 'run-b',
  lostInputs: [],
  rows: [
    {
      edgeVariant: 'main',
      variant: 'momentum_12_1',
      role: 'screener',
      horizonSessions: 21,
      sliceKind: 'frozen',
      sliceValue: '2024-01-01',
      sessions: 120,
      picks: 2400,
      hits: 1392,
      trials: 4,
      hitRate: 0.58,
      baseRate: 0.51,
      lift: 1.14,
      decileSpread: 0.012,
      exploratory: false,
    },
  ],
};

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function open(page: Page, overrides = {}) {
  await mockRegimeApi(page); // the top-bar chip reads the regime
  await mockViewer(page);
  await mockNoGuideEntries(page);
  await mockAdminApi(page, { harnessRuns: RUNS, 'harnessRun:run-b': ROWS, ...overrides });
}

for (const theme of ['dark', 'light'] as const) {
  test(`lists the runs and a chosen run's rows (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await open(page);
    await page.goto('/admin/harness-runs?run=run-b');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'Harness runs' })).toBeVisible();
    const list = page.getByRole('grid', { name: 'Harness runs' });
    await expect(list).toContainText('run-a');
    await expect(list).toContainText('EXPLORATORY');
    await expect(page.getByRole('grid', { name: 'Run rows' })).toContainText('58.0%');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a run opens its rows and the choice is in the URL', async ({ page }) => {
  await open(page);
  await page.goto('/admin/harness-runs');
  await page.getByRole('row', { name: /run-b/ }).click();
  await expect(page).toHaveURL(/run=run-b/);
  await expect(page.getByRole('grid', { name: 'Run rows' })).toContainText('momentum_12_1');
});

test('a failed read shows its error with a retry', async ({ page }) => {
  await open(page, { harnessRuns: FAIL });
  await page.goto('/admin/harness-runs');
  await expect(page.getByText('The harness runs failed to load.').first()).toBeVisible();
});
