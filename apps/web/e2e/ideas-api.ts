/**
 * Playwright route mock for the Ideas page: the `IdeasPage` GraphQL operation (POST
 * /api/graphql) answers from the fixture (e2e/fixtures/ideas/ideas-page.json, shaped from the
 * schema's `Ideas`); the `EdgeDesk` operation (the followed edges' signals) answers with no
 * followed edge unless a test gives it a desk; any other operation falls through to the other
 * areas' mocks.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

const FIXTURE: unknown = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/ideas/ideas-page.json', import.meta.url)), 'utf8'),
);

/** The signals of a user who follows nothing (the Ideas page then shows one line). */
export const NO_EDGE_DESK = { data: { edgeDesk: null } };

export async function mockIdeasApi(page: Page, edgeDesk: unknown = NO_EDGE_DESK): Promise<void> {
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as { query?: string } | null;
    if (/query\s+EdgeDesk\b/.test(body?.query ?? '')) {
      await route.fulfill({ json: edgeDesk });
      return;
    }
    if (!/query\s+IdeasPage\b/.test(body?.query ?? '')) {
      await route.fallback();
      return;
    }
    await route.fulfill({ json: FIXTURE });
  });
}
