/**
 * The whole API mocked for end-to-end tests: one handler per page area answering from fixtures
 * recorded from the real API (Explore: explore-api.ts; Admin: admin-api.ts). Any `/api` call
 * no area answers is a 404 with a detail, so a test that reaches a new page fails loudly.
 * Playwright tries the most recently added route first, so the narrower admin route wins.
 */
import type { Page } from '@playwright/test';

import { mockAdminApi } from './admin-api';
import { mockExploreApi } from './explore-api';

export async function mockApi(page: Page): Promise<void> {
  await mockExploreApi(page);
  await mockAdminApi(page);
}
