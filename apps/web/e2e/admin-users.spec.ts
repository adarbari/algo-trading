/**
 * Admin › Users end to end against a mocked API: the declared people with their role and licences
 * (never an email), accessible in dark and light; a failed read shows its error.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockNoGuideEntries } from './admin-api';
import { mockViewer } from './auth-api';
import { mockRegimeApi } from './regime-api';

const PEOPLE = [
  { id: 'abhi', name: 'Abhi Admin', role: 'admin', licences: ['personal'], scheduled: false },
  { id: 'tess', name: 'Tess Trader', role: 'trader', licences: [], scheduled: false },
  { id: 'site', name: 'Scheduled site screens', role: 'admin', licences: [], scheduled: true },
];

async function mockRegistry(page: Page, answer: 'ok' | 'fail'): Promise<void> {
  await page.route('**/api/graphql', async (route) => {
    const body = route.request().postDataJSON() as { query?: string } | null;
    if (!/query\s+UserRegistry\b/.test(body?.query ?? '')) {
      await route.fallback();
      return;
    }
    await route.fulfill(
      answer === 'ok'
        ? { json: { data: { userRegistry: { people: PEOPLE } } } }
        : { json: { errors: [{ message: 'boom' }], data: null } },
    );
  });
}

for (const theme of ['dark', 'light'] as const) {
  test(`lists the declared people (${theme})`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await mockRegimeApi(page);
    await mockViewer(page);
    await mockNoGuideEntries(page);
    await mockRegistry(page, 'ok');
    await page.goto('/admin/users');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'Users' })).toBeVisible();
    const table = page.getByRole('grid', { name: 'People' });
    await expect(table).toContainText('Tess Trader');
    await expect(table).toContainText('personal');
    await expect(page.getByLabel('People summary').first()).toContainText('2');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a failed read shows its error', async ({ page }) => {
  await mockRegimeApi(page);
  await mockViewer(page);
  await mockNoGuideEntries(page);
  await mockRegistry(page, 'fail');
  await page.goto('/admin/users');
  await expect(page.getByText('The people failed to load.')).toBeVisible();
});
