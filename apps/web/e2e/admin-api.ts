/**
 * A mocked admin API for end-to-end tests: Playwright answers `/api/admin/*` from fixture JSON
 * shaped from real responses (admin-ingestion.fixtures.json); unknown paths are 404s.
 */
import type { Page } from '@playwright/test';

import fixtures from './admin-ingestion.fixtures.json' with { type: 'json' };

export type AdminFixtures = Record<string, unknown>;

export const ADMIN_FIXTURES = fixtures as AdminFixtures;

export async function mockAdminApi(page: Page, overrides: AdminFixtures = {}): Promise<void> {
  const routes = { ...ADMIN_FIXTURES, ...overrides };
  await page.route('**/api/admin/**', async (route) => {
    const path = decodeURIComponent(new URL(route.request().url()).pathname).replace(/^\/api/, '');
    const body = routes[path];
    await (body === undefined
      ? route.fulfill({ status: 404, json: { detail: `no fixture for ${path}` } })
      : route.fulfill({ json: body }));
  });
}
