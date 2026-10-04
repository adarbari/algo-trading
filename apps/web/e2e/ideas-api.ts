/**
 * Playwright route mock for the Ideas page: GET /api/ideas answers from the fixture
 * (e2e/fixtures/ideas/ideas.json, shaped from the API's `Ideas` schema), reflecting the
 * priority saved with PUT /api/preferences/ideas. `failSave` makes the PUT fail with a 500.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

type Json = Record<string, unknown>;

const FIXTURE = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/ideas/ideas.json', import.meta.url)), 'utf8'),
) as Json;

export interface IdeasMockOptions {
  /** Answer PUT /preferences/ideas with a server error. */
  failSave?: boolean;
}

/** The saved bodies of PUT /preferences/ideas, in order (for assertions). */
export interface IdeasMock {
  saved: string[][];
}

export async function mockIdeasApi(page: Page, options: IdeasMockOptions = {}): Promise<IdeasMock> {
  let priority = FIXTURE['priority'] as string[];
  const mock: IdeasMock = { saved: [] };
  await page.route('**/api/ideas*', (route: Route) =>
    route.fulfill({ json: { ...FIXTURE, priority } }),
  );
  await page.route('**/api/preferences/ideas*', async (route: Route) => {
    if (options.failSave) {
      await route.fulfill({ status: 500, json: { detail: 'preferences store unavailable' } });
      return;
    }
    const body = route.request().postDataJSON() as { priority: string[] };
    priority = body.priority;
    mock.saved.push(body.priority);
    await route.fulfill({ json: { priority } });
  });
  return mock;
}
