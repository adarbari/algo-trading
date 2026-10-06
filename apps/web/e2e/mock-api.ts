/**
 * The whole API mocked for end-to-end tests: one handler per page area answering from fixtures
 * recorded from the real API (Explore: explore-api.ts; Admin: admin-api.ts; Ideas: ideas-api.ts; Screeners: builder-api.ts). Any `/api` call
 * no area answers is a 404 with a detail, so a test that reaches a new page fails loudly.
 * Playwright tries the most recently added route first, so the narrower admin route wins; the
 * viewer (auth-api.ts) is added last because the areas answer any other GraphQL operation 404.
 */
import type { Page } from '@playwright/test';

import { mockAdminApi } from './admin-api';
import { mockViewer } from './auth-api';
import { mockBuilderApi } from './builder-api';
import { mockExploreApi } from './explore-api';
import { mockIdeasApi } from './ideas-api';

export async function mockApi(page: Page): Promise<void> {
  await mockExploreApi(page);
  await mockAdminApi(page);
  await mockIdeasApi(page);
  await mockBuilderApi(page);
  // Last, so it is tried first: the API as with ALGOTRADE_AUTH=off (the viewer answers, no token).
  await mockViewer(page);
}
