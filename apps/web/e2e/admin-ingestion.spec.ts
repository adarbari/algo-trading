/**
 * Admin › Ingestion end to end against a mocked API (fixtures shaped from real responses): the
 * summary, the completeness grid and its drill-down (deep-linked in the URL), the run record
 * drawer, the CSV download, quality checks, verification vs IBKR, review items and recent runs,
 * accessible in dark and light; the stale-data banner; a failed section shows its error.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { ADMIN_FIXTURES, mockAdminApi } from './admin-api';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

for (const theme of ['dark', 'light'] as const) {
  test(`shows completeness, quality and verification (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await mockAdminApi(page);
    await page.goto('/admin/ingestion');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    const summary = page.getByLabel('Ingestion summary');
    await expect(summary.first()).toContainText('98.9%');
    await expect(summary.first()).toContainText('4 pass · 1 fail');
    const grid = page.getByRole('grid', { name: 'Completeness by dataset and session' });
    await expect(grid).toContainText('Option chains');
    await expect(page.getByRole('heading', { name: 'Option chains · Fri 2 Oct' })).toBeVisible();
    await expect(page.getByText('3,623 of 4,203 expected', { exact: false })).toBeVisible();
    await expect(page.getByRole('grid', { name: 'Quality checks' })).toContainText(
      'chains_coverage',
    );
    await expect(page.getByRole('grid', { name: 'Failing verification checks' })).toContainText(
      'SPY',
    );
    await expect(page.getByRole('grid', { name: 'Recent nightly runs' })).toContainText('26m 0s');
    await expect(page.getByText('Latest session not ingested')).toHaveCount(0);
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a cell drills in, opens its run record and downloads its items', async ({ page }) => {
  const errors = collectErrors(page);
  await mockAdminApi(page, {
    '/admin/ingestion/bars/1d/2026-10-02': {
      ...(ADMIN_FIXTURES['/admin/ingestion/chains/option_quotes/2026-10-02'] as object),
      cell: {
        dataset: 'bars/1d',
        session: '2026-10-02',
        status: 'COMPLETE',
        present: 12601,
        expected: 12594,
        basis: 'rows on 2026-10-01',
        run_ids: [],
      },
    },
  });
  await page.goto('/admin/ingestion');
  await page.getByRole('gridcell', { name: /^Daily bars, Fri 2:/ }).click();
  await expect(page).toHaveURL(/dataset=bars%2F1d&session=2026-10-02/);
  await expect(page.getByRole('heading', { name: 'Daily bars · Fri 2 Oct' })).toBeVisible();

  await page.getByRole('button', { name: 'Open run record' }).click();
  const drawer = page.getByRole('dialog', { name: 'Run record' });
  await expect(drawer).toContainText('option_chains');
  await expect(drawer.getByRole('grid', { name: 'Run items' })).toContainText('EQ:ACIU');
  await page.keyboard.press('Escape');

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download items (CSV)' }).click();
  expect((await download).suggestedFilename()).toBe(
    'option_chains-2026-10-02-20261003T093502Z-items.csv',
  );
  await expect(page.getByText('25 items saved')).toBeVisible();
  await expect(page.getByRole('button', { name: /Re-run daily bars/ })).toBeDisabled();
  expect(errors).toEqual([]);
});

test('warns when the latest session is not ingested; a failed section shows its error', async ({
  page,
}) => {
  await mockAdminApi(page, {
    '/admin/ingestion/completeness': {
      ...(ADMIN_FIXTURES['/admin/ingestion/completeness'] as object),
      last_closed: '2026-10-05',
    },
    '/admin/verification/ibkr': undefined,
  });
  await page.route('**/api/admin/quality', (route) =>
    route.fulfill({ status: 500, json: { detail: 'store unavailable' } }),
  );
  await page.goto('/admin/ingestion');
  await expect(page.getByText(/Latest session not ingested/)).toBeVisible();
  await expect(page.getByText('Quality checks could not load.')).toBeVisible();
  await expect(page.getByText('No verification run yet')).toBeVisible();
});
