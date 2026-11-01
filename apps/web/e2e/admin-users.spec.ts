/**
 * Admin › Users end to end against a mocked API: the declared people with their role and licences
 * (never an email), accessible in dark and light; a failed read shows its error.
 */
import { expect, test } from '@playwright/test';

import { expectAccessible } from './a11y';
import { FAIL, mockAdminApi, mockNoGuideEntries } from './admin-api';
import { mockViewer } from './auth-api';
import { mockRegimeApi } from './regime-api';

const PEOPLE = [
  { id: 'abhi', name: 'Abhi Admin', role: 'admin', licences: ['personal'], scheduled: false },
  { id: 'tess', name: 'Tess Trader', role: 'trader', licences: [], scheduled: false },
  { id: 'site', name: 'Scheduled site screens', role: 'admin', licences: [], scheduled: true },
];

for (const theme of ['dark', 'light'] as const) {
  test(`lists the declared people (${theme})`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await mockRegimeApi(page);
    await mockViewer(page);
    await mockNoGuideEntries(page);
    await mockAdminApi(page, { userRegistry: { people: PEOPLE } });
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
  await mockAdminApi(page, { userRegistry: FAIL });
  await page.goto('/admin/users');
  await expect(page.getByText('The people failed to load.')).toBeVisible();
});
