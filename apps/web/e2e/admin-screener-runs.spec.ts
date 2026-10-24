/**
 * Admin > Screener runs end to end against a mocked API: the runs list of any status (an
 * unrecorded figure stays empty), a run's record beside it (the choice and the filters live in
 * the URL), accessible in dark and light; a failed read shows its error.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { FAIL, mockAdminApi, mockNoGuideEntries } from './admin-api';
import { mockViewer } from './auth-api';
import { mockRegimeApi } from './regime-api';

const RUNS = [
  {
    runId: 'screen-trend-site',
    configId: 'trend_pullback',
    owner: 'site',
    session: '2026-10-22',
    status: 'COMPLETE',
    startedAt: '2026-10-22T22:05:00+00:00',
    finishedAt: '2026-10-22T22:07:00+00:00',
    knowledgeTs: '2026-10-22T22:07:00+00:00',
    picked: 12,
    paused: 3,
    regime: 'Risk on',
    coverage: '480 of 500 screened',
  },
  {
    runId: 'screen-value-abhi',
    configId: 'value_dip',
    owner: 'abhi',
    session: '2026-10-21',
    status: 'FAILED',
    startedAt: '2026-10-21T22:05:00+00:00',
    finishedAt: null,
    knowledgeTs: '2026-10-21T22:05:00+00:00',
    picked: null,
    paused: null,
    regime: null,
    coverage: null,
  },
];

const RUN = {
  ...RUNS[0],
  configVersion: 3,
  configHash: 'a1b2c3d4',
  decisions: [
    { decision: 'qualified', count: 12 },
    { decision: 'watch', count: 5 },
  ],
  missingTables: [],
  missingOptionalTables: ['rollups/instrument/ibkr_iv@v1'],
  unavailable: [],
  changes: {
    picked: 12,
    paused: 3,
    previousRunId: 'screen-trend-site-0',
    previousSession: '2026-10-21',
    previousVersion: 3,
    newPicks: 4,
    dropped: 2,
  },
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
  await mockAdminApi(page, {
    screenerRuns: RUNS,
    'screenerRun:screen-trend-site': RUN,
    ...overrides,
  });
}

for (const theme of ['dark', 'light'] as const) {
  test(`lists the runs and a chosen run's record (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await open(page);
    await page.goto('/admin/screener-runs?run=screen-trend-site');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'Screener runs' })).toBeVisible();
    const list = page.getByRole('grid', { name: 'Screener runs' });
    await expect(list).toContainText('value_dip');
    await expect(list).toContainText('failed');
    await expect(page.getByLabel('Run', { exact: true })).toContainText('version 3, hash a1b2c3d4');
    await expect(page.getByLabel('Changes')).toContainText('screen-trend-site-0');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a run opens its record and the choice is in the URL', async ({ page }) => {
  await open(page);
  await page.goto('/admin/screener-runs');
  await page.getByRole('row', { name: /trend_pullback/ }).click();
  await expect(page).toHaveURL(/run=screen-trend-site/);
  await expect(page.getByLabel('Decisions')).toContainText('qualified');
});

test('a status filter is sent to the server and kept in the URL', async ({ page }) => {
  await open(page);
  const asked: unknown[] = [];
  await page.route('**/api/graphql', async (route) => {
    const body = route.request().postDataJSON() as { variables?: Record<string, unknown> };
    if (body.variables && 'status' in body.variables) asked.push(body.variables['status']);
    await route.fallback();
  });
  await page.goto('/admin/screener-runs?status=failed');
  await expect(page.getByRole('grid', { name: 'Screener runs' })).toBeVisible();
  expect(asked).toContain('FAILED');
});

test('a failed read shows its error with a retry', async ({ page }) => {
  await open(page, { screenerRuns: FAIL });
  await page.goto('/admin/screener-runs');
  await expect(page.getByText('The screener runs failed to load.').first()).toBeVisible();
});
