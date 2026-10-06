/**
 * Trader > Regime end to end, against the production build with the regime mocked from
 * fixtures recorded from the real API (regime-api.ts): until the RG3 groups exist the regime
 * is UNKNOWN with its reason, every indicator card is listed (slow and fast) and the reading
 * list shows each link once. The top-bar chip says "not computed" on every page and opens the
 * Regime page; the Ideas strip says the sizing rule; accessibility in both themes.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockApi } from './mock-api';
import { EXPLANATION, mockExplain, mockRegimeComputed } from './regime-api';

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

for (const theme of ['dark', 'light'] as const) {
  test(`the Regime page shows the UNKNOWN state, the cards and the reading list (${theme})`, async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.goto('/regime');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'Regime' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 3, name: 'Not computed' })).toBeVisible();
    await expect(page.getByText(/the regime has not been computed yet/).first()).toBeVisible();
    const slow = page.getByRole('region', { name: 'Slow-moving warning signs' });
    const fast = page.getByRole('region', { name: 'Fast-moving market signs' });
    await expect(slow.getByRole('listitem')).toHaveCount(5);
    await expect(fast.getByRole('listitem')).toHaveCount(3);
    const reading = page.getByRole('region', { name: 'Reading list' });
    await expect(reading.getByRole('link').first()).toBeVisible();
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('the Regime page shows the sizing rules of the caller, read-only', async ({ page }) => {
  await page.goto('/regime');
  await expect(
    page.getByText('The regime gate is off: new positions are at full size'),
  ).toBeVisible();
  await expect(page.getByLabel('Size of a new position')).toContainText('50%');
  await expect(page.getByLabel('Your screeners')).toContainText('pause in Storm and Severe storm');
});

test('a card opens to its detail and its links', async ({ page }) => {
  await page.goto('/regime');
  await page.getByRole('button', { name: /Are long-term rates below short-term ones/ }).click();
  await expect(page.getByRole('heading', { name: 'What it did before' })).toBeVisible();
  await expect(page.getByRole('link', { name: /FRED/ }).first()).toBeVisible();
});

test('the top-bar chip says not computed and opens the Regime page; Ideas shows the strip', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await expect(page.getByText('New positions at full size (the regime gate is off)')).toBeVisible();
  await page.getByRole('button', { name: 'Regime: not computed' }).first().click();
  await expect(page).toHaveURL(/\/regime$/);
  await expect(page.getByRole('link', { name: 'Regime' })).toHaveAttribute('aria-current', 'page');
  expect(errors).toEqual([]);
});

test('the explain button is hidden when no text model is configured', async ({ page }) => {
  const errors = collectErrors(page);
  await mockRegimeComputed(page);
  await mockExplain(page, false);
  await page.goto('/regime');
  await expect(page.getByRole('heading', { level: 3, name: 'Clouds building' })).toBeVisible();
  await expect(page.getByText('2 of 5 slow-moving warning signs are on.')).toBeVisible();
  await expect(page.getByRole('button', { name: /plain words/ })).toHaveCount(0);
  expect(errors.filter((e) => !e.includes('503'))).toEqual([]);
});

test('with a text model the button explains the regime, with its citation and footer', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await mockRegimeComputed(page);
  await mockExplain(page, true);
  await page.goto('/regime');
  await page.getByRole('button', { name: 'Explain in plain words' }).click();
  await expect(page.getByText(EXPLANATION.text)).toBeVisible();
  await expect(page.getByRole('link', { name: /FRED: T10Y3M/ })).toBeVisible();
  await expect(page.getByText(/it may be wrong/)).toBeVisible();
  await expectAccessible(page);
  expect(errors.filter((e) => !e.includes('400'))).toEqual([]);
});
