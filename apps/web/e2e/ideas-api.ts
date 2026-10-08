/**
 * Playwright route mock for the Ideas page: the `IdeasPage` GraphQL operation (POST
 * /api/graphql) answers from the fixture (e2e/fixtures/ideas/ideas-page.json, shaped from the
 * schema's `Ideas`); any other operation falls through to the other areas' mocks.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

const FIXTURE: unknown = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/ideas/ideas-page.json', import.meta.url)), 'utf8'),
);

export async function mockIdeasApi(page: Page): Promise<void> {
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as { query?: string } | null;
    if (!/query\s+IdeasPage\b/.test(body?.query ?? '')) {
      await route.fallback();
      return;
    }
    await route.fulfill({ json: FIXTURE });
  });
}
