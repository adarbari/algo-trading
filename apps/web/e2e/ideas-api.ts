/**
 * Playwright route mock for the Ideas page: the `IdeasPage` GraphQL operation (POST
 * /api/graphql) answers from the fixture (e2e/fixtures/ideas/ideas-page.json, shaped from the
 * schema's `Ideas`), with the screeners in the priority saved with PUT /api/preferences/ideas
 * (the server orders them); any other operation falls through to the other areas' mocks.
 * `failSave` makes the PUT fail with a 500.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

interface Screener {
  screener: { id: string };
}
interface Fixture {
  data: { ideas: { priority: string[]; screeners: Screener[] } & Record<string, unknown> };
}

const FIXTURE = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('./fixtures/ideas/ideas-page.json', import.meta.url)),
    'utf8',
  ),
) as Fixture;

export interface IdeasMockOptions {
  /** Answer PUT /preferences/ideas with a server error. */
  failSave?: boolean;
}

/** The saved bodies of PUT /preferences/ideas, in order (for assertions). */
export interface IdeasMock {
  saved: string[][];
}

function answer(priority: readonly string[]): Fixture {
  const ideas = FIXTURE.data.ideas;
  const place = (id: string) => {
    const index = priority.indexOf(id);
    return index < 0 ? priority.length : index;
  };
  const screeners = [...ideas.screeners].sort(
    (a, b) => place(a.screener.id) - place(b.screener.id),
  );
  return { data: { ideas: { ...ideas, priority: [...priority], screeners } } };
}

export async function mockIdeasApi(page: Page, options: IdeasMockOptions = {}): Promise<IdeasMock> {
  let priority = FIXTURE.data.ideas.priority;
  const mock: IdeasMock = { saved: [] };
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as { query?: string } | null;
    if (!/query\s+IdeasPage\b/.test(body?.query ?? '')) {
      await route.fallback();
      return;
    }
    await route.fulfill({ json: answer(priority) });
  });
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
