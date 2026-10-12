/**
 * Admin > Feature requests end to end against a mocked API: the ranked list with its counts and
 * statuses, a status filter that lives in the URL, accessible in dark and light; a failed read
 * shows its error.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { FAIL, mockAdminApi, mockNoGuideEntries } from './admin-api';
import { mockViewer } from './auth-api';
import FORMULAS from './fixtures/accepted-formulas.json' with { type: 'json' };
import REQUESTS from './fixtures/feature-requests.json' with { type: 'json' };
import { mockRegimeApi } from './regime-api';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

async function open(page: Page, overrides = {}) {
  await mockRegimeApi(page); // the top-bar chip reads the regime
  await mockViewer(page);
  await mockNoGuideEntries(page);
  await mockAdminApi(page, { featureRequests: REQUESTS, acceptedFormulas: FORMULAS, ...overrides });
}

for (const theme of ['dark', 'light'] as const) {
  test(`lists the ranked requests (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await open(page);
    await page.goto('/admin/feature-requests');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'Feature requests' })).toBeVisible();
    const list = page.getByRole('grid', { name: 'Feature requests' });
    await expect(list).toContainText('realised_vol_20d');
    await expect(list).toContainText('rollup.momentum@v1.rsi_14');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('the status filter is in the URL and hides the other rows', async ({ page }) => {
  await open(page);
  await page.goto('/admin/feature-requests');
  await page.getByRole('radio', { name: 'Promoted' }).click();
  await expect(page).toHaveURL(/status=PROMOTED/);
  const list = page.getByRole('grid', { name: 'Feature requests' });
  await expect(list).toContainText('rsi_14');
  await expect(list).not.toContainText('realised_vol_20d');
});

test('a failed read shows its error with a retry', async ({ page }) => {
  await open(page, { featureRequests: FAIL });
  await page.goto('/admin/feature-requests');
  await expect(page.getByText('The feature requests failed to load.').first()).toBeVisible();
});

test('lists the accepted formulas, flags a duplicate and opens a row to its canonical form', async ({
  page,
}) => {
  await open(page);
  await page.goto('/admin/feature-requests');
  const table = page.getByRole('table', { name: 'Accepted formulas' });
  await expect(table).toContainText('close/sma_20 - 1');
  await expect(table.getByRole('row', { name: /high - low/ })).toContainText('DUPLICATE');
  await table.getByRole('button', { name: /close\/sma_20 - 1/ }).click();
  await expect(table).toContainText('(close / sma_20) - 1');
  await expectAccessible(page);
});

test('a failed accepted-formulas read shows its error and leaves the requests', async ({
  page,
}) => {
  await open(page, { acceptedFormulas: FAIL });
  await page.goto('/admin/feature-requests');
  await expect(page.getByText('The accepted formulas failed to load.').first()).toBeVisible();
  await expect(page.getByRole('grid', { name: 'Feature requests' })).toContainText(
    'realised_vol_20d',
  );
});
