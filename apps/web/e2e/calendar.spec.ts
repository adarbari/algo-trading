/**
 * Trader > Calendar and the Explore Events tab end to end, against the production build with
 * the event study mocked (events-api.ts): the Calendar page lists the scope list by default (a
 * Market column, the expiry Friday ruled), switches to a screener's picks and asks the API for
 * exactly those names; the Events tab shows what is coming, the ladder with its marked rung,
 * the 8-K, and for a fund the reference link and the reasons for what is not known.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockEventsApi } from './events-api';
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

test('the Calendar page shows the scope list, then the picks of a screener', async ({ page }) => {
  const errors = collectErrors(page);
  const events = await mockEventsApi(page);
  await page.goto('/calendar');
  await expect(page.getByRole('heading', { level: 1, name: 'Calendar' })).toBeVisible();
  const grid = page.getByRole('table', { name: 'Events, next 90 days: scope list' });
  await expect(grid).toBeVisible();
  await expect(grid.getByRole('columnheader', { name: 'Market' })).toBeVisible();
  await expect(grid.getByRole('columnheader', { name: 'AAPL' })).toBeVisible();
  await expect(grid.getByText('Expiry', { exact: true })).toBeVisible();
  expect(events.calendarAsked[0]).toEqual({ instrumentIds: [], scope: true });
  await expectAccessible(page);
  await page.getByLabel('Names').selectOption('vrp_scanner');
  await expect(
    page.getByRole('table', { name: 'Events, next 90 days: vrp_scanner' }),
  ).toBeVisible();
  const last = events.calendarAsked.at(-1);
  expect(last?.scope).toBe(false);
  expect(last?.instrumentIds).toContain('EQ:AAPL');
  expect(errors).toEqual([]);
});

test('the top bar reaches the Calendar', async ({ page }) => {
  await page.goto('/ideas');
  await page.getByRole('link', { name: 'Calendar' }).click();
  await expect(page).toHaveURL(/\/calendar$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Calendar' })).toBeVisible();
});

test('the Events tab shows what is coming, the ladder and the filings', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/explore?focus=AAPL&tab=events');
  const ahead = page.getByRole('grid', { name: 'Events ahead for AAPL' });
  await expect(ahead.getByText('Earnings').first()).toBeVisible();
  await expect(ahead.getByText('Monthly expiry')).toBeVisible();
  await expect(page.getByRole('table', { name: /AAPL expiries/ })).toBeVisible();
  const filings = page.getByRole('grid', { name: 'AAPL filings list' });
  await expect(filings.getByText('Results')).toBeVisible();
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('a fund tracks its reference and says what is not known', async ({ page }) => {
  await page.goto('/explore?focus=SOXS&tab=events');
  await expect(page.getByText('Tracks NVDA')).toBeVisible();
  await expect(
    page.getByText('Expiry ladder: Unknown (no option chain stored for the session)'),
  ).toBeVisible();
  await expect(page.getByText('Filings: n/a (a fund files no 8-Ks)')).toBeVisible();
  await page.getByRole('button', { name: 'Open NVDA' }).click();
  await expect(page).toHaveURL(/focus=NVDA/);
});
