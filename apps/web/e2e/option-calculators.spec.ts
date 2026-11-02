/**
 * Explore > Roll a put, Calls on shares and Buying power end to end, against the production build with the API
 * mocked (explore-api.ts): type a contract, see the buy-back sentence and the rolls with
 * Basics and More and "See all", type shares and a price, see the calls with their flags, the muted
 * call below the price and the dividend, and that neither tab puts what was typed in the URL.
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

test('Roll a put: the contract in, the buy-back sentence and the rolls out', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/explore?focus=AAPL&tab=roll');
  await page.getByRole('spinbutton', { name: 'Strike' }).fill('80');
  await page.getByRole('combobox', { name: 'Expiry' }).selectOption('2026-10-30');
  await page.getByRole('spinbutton', { name: /Sold at/ }).fill('1.4');
  await page.getByRole('button', { name: 'Show rolls' }).click();
  await expect(page.getByText(/Buying it back now costs \$1\.85/)).toBeVisible();
  const table = page.getByRole('grid', { name: 'AAPL rolls for a credit' });
  await expect(table.getByRole('row')).toHaveCount(1 + 4);
  await expect(table.getByText('Includes report')).toBeVisible();
  await page.getByRole('button', { name: 'See all 5' }).click();
  await expect(table.getByRole('row')).toHaveCount(1 + 5);
  await page.getByRole('radio', { name: 'More' }).click();
  await expect(page.getByRole('checkbox', { name: 'Include rolls that cost money' })).toBeVisible();
  expect(page.url()).not.toContain('80');
  await expectAccessible(page);
  expect(errors).toEqual([]);
  await page.getByRole('button', { name: 'Calls on shares' }).click();
  await expect(page).toHaveURL(/tab=calls/);
});

test('Calls on shares: the calls with their flags, the muted one labelled, and the dividend', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/explore?focus=AAPL&tab=calls');
  await page.getByRole('spinbutton', { name: 'Shares you hold' }).fill('300');
  await page.getByRole('spinbutton', { name: /Your price/ }).fill('78.5');
  await page.getByRole('button', { name: 'Show calls' }).click();
  await expect(page.getByText('AAPL closed at $84.20, 7.3% above your price.')).toBeVisible();
  const table = page.getByRole('grid', { name: 'AAPL calls you could sell' });
  await expect(table.getByText('below your price')).toHaveCount(1);
  await expect(table.getByText('Early exercise risk')).toBeVisible();
  await expect(page.getByText('Next ex-dividend date 12 Nov 2026, $0.62 a share.')).toBeVisible();
  expect(page.url()).not.toContain('300');
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('Buying power: the contract in, what it ties up in each account, size and stress out', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/explore?focus=AAPL&tab=margin');
  await page.getByRole('spinbutton', { name: 'Strike' }).fill('80');
  await page.getByRole('combobox', { name: 'Expiry' }).selectOption('2026-11-20');
  await page.getByRole('spinbutton', { name: 'Contracts' }).fill('2');
  await page.getByRole('button', { name: 'Calculate' }).click();
  await expect(page.getByText('$3,600.00')).toBeVisible();
  await expect(page.getByText('Cash-secured would hold $16,000.00')).toBeVisible();
  await expect(page.getByText(/Covid crash, early 2020, −34%/)).toBeVisible();
  await page.getByRole('radio', { name: 'Cash-secured' }).click();
  await expect(page.getByText('Margin account would hold $3,600.00')).toBeVisible();
  expect(page.url()).not.toContain('80');
  await expectAccessible(page);
  expect(errors).toEqual([]);
});
