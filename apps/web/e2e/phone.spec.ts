/**
 * The app on a phone (iPhone 13: touch, 390 px wide; the `phone` project of playwright.config.ts,
 * ADR 0025 rule 10), against the production build with the API mocked: every top-bar route fits
 * the screen (no horizontal page scroll, a top bar that does not eat it), logs no errors and is
 * accessible; a ticker opens its detail as a sheet; a screener name opens its results; the chart
 * has zoom buttons for fingers.
 */
import { expect, test, type Page } from '@playwright/test';

import { WORKSPACES } from '../src/app/workspaces/workspaces';
import { expectAccessible, settled } from './a11y';
import { mockApi } from './mock-api';

const ROUTES = WORKSPACES.flatMap((w) => w.sections.map((s) => s.path));
/** The top bar may take at most this share of the viewport height. */
const TOP_BAR_SHARE = 0.3;

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
    expect(bar?.height ?? 0).toBeLessThan(innerHeight * TOP_BAR_SHARE);
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
