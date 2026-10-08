/**
 * Admin › LLM usage & cost end to end against a mocked API: the spend tiles and the cap meters,
 * the breakdown by cost basis, the reliability strip, the recent calls and a call's detail
 * (deep-linked in the URL), accessible in dark and light; a failed read shows its error.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { FAIL, mockAdminApi } from './admin-api';
import { mockViewer } from './auth-api';
import { mockRegimeApi } from './regime-api';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

for (const theme of ['dark', 'light'] as const) {
  test(`shows the spend against the budget and the recent calls (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await mockRegimeApi(page); // the top-bar chip reads the regime
    await mockViewer(page);
    await mockAdminApi(page);
    await page.goto('/admin/llm-usage');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'LLM usage & cost' })).toBeVisible();
    const strip = page.getByRole('region', { name: 'Spend by window' });
    await expect(strip).toContainText('$0.7527');
    await expect(strip).toContainText('notional (reported)');
    await expect(page.getByRole('meter', { name: /Today against the daily cap/ })).toBeVisible();
    await expect(page.getByRole('region', { name: 'How attempts ended' })).toContainText(
      'Fell back',
    );
    await expect(page.getByRole('grid', { name: 'Recent text-model calls' })).toContainText(
      'claude_cli',
    );
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a call opens its detail and the choice is in the URL', async ({ page }) => {
  const errors = collectErrors(page);
  await mockRegimeApi(page);
  await mockViewer(page);
  await mockAdminApi(page);
  await page.goto('/admin/llm-usage');
  await page.getByText('2026-10-08 13:00:00 UTC').click();
  await expect(page).toHaveURL(/call=/);
  await expect(page.getByText('Not known: Input tokens, Output tokens')).toBeVisible();
  expect(errors).toEqual([]);
});

test('a failed read shows its error with a retry', async ({ page }) => {
  await mockRegimeApi(page);
  await mockViewer(page);
  await mockAdminApi(page, { llmUsage: FAIL });
  await page.goto('/admin/llm-usage');
  await expect(page.getByText('Text-model usage could not load.').first()).toBeVisible();
});
