/**
 * Trader > Edges end to end, against the production build with the edges mocked (edges-api.ts):
 * the list shows each edge under its verdict, the chosen edge's page shows the verdict, the
 * out-of-sample figures and the details (an exploratory run is labelled and never shown as
 * figures), and the chosen edge lives in the URL; the Screeners list shows a track-record chip and Ideas an odds line for a
 * screener a candidate edge lists.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockApi } from './mock-api';

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

test('the Edges tab lists the edges and the chosen edge shows its verdict and figures', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await page.getByRole('navigation', { name: 'Trader sections' }).getByText('Edges').click();
  await expect(page).toHaveURL(/\/edges$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Edges' })).toBeVisible();
  const list = page.getByRole('grid', { name: 'Edges' });
  await expect(list.getByRole('row', { name: /Momentum 12-1/ })).toContainText('Promising');
  await expect(list.getByRole('row', { name: /S&P 500 index changes/ })).toContainText(
    'Waiting on data',
  );
  await list.getByRole('row', { name: /Momentum 12-1/ }).click();
  await expect(page).toHaveURL(/\/edges\?edge=momentum_12_1$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Momentum 12-1' })).toBeVisible();
  await expect(page.getByText('+7 pts').first()).toBeVisible();
  await page.getByText('Details').click();
  await expect(page.getByText('EXPLORATORY')).toBeVisible();
  await expect(page.getByText('99.0%')).toHaveCount(0);
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('a user sets and clears their out-of-sample split', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/edges?edge=momentum_12_1');
  await page.getByText('Details').click();
  await expect(page.getByText('2026-06-01').first()).toBeVisible();
  await page.getByLabel('Out-of-sample starts').fill('2026-04-01');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(/labelled EXPLORATORY and come from evaluate-edges/)).toBeVisible();
  await expect(page.getByText('2026-04-01').first()).toBeVisible();
  await page.getByRole('button', { name: 'Clear' }).click();
  await expect(page.getByText(/Cleared/)).toBeVisible();
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('a user runs an evaluation of the chosen edge and sees it finish', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/edges?edge=momentum_12_1');
  await page.getByRole('button', { name: 'Run backtest' }).click();
  await expect(page.getByText('Done (exploratory)')).toBeVisible();
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('Screeners shows the track record of a screener in an edge', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/screeners');
  await expect(page.getByText(/vs \d+% base/).first()).toBeVisible();
  await expect(page.getByText(/^Edge: /).first()).toBeVisible();
  expect(errors).toEqual([]);
});
