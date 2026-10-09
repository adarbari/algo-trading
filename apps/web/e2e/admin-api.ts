/**
 * A mocked admin API for end-to-end tests: Playwright answers the Admin GraphQL reads
 * (`POST /api/graphql`: completeness, ingestionCell, quality, verification, nightlyRuns, run,
 * runItems, figiReview, leverageReview, llmUsage, harnessRuns, harnessRun) from fixture JSON shaped from real responses
 * (admin-ingestion.fixtures.json), keyed by the operation's Query field, or `field:<key>` for
 * a field read by key (`ingestionCell:<dataset>/<date>`, `run:<id>`, `runItems:<id>`). A field
 * with no fixture is null (nothing stored, no such thing); `FAIL` answers a GraphQL error.
 * Other operations fall through to the next mock.
 */
import type { Page, Route } from '@playwright/test';

import fixtures from './admin-ingestion.fixtures.json' with { type: 'json' };

export type AdminFixtures = Record<string, unknown>;

export const ADMIN_FIXTURES = fixtures as AdminFixtures;

/** An override value: the field answers a GraphQL error. */
export const FAIL = 'FAIL';

const FIELDS = new Set([
  'completeness',
  'ingestionCell',
  'quality',
  'verification',
  'nightlyRuns',
  'run',
  'runItems',
  'figiReview',
  'leverageReview',
  'llmUsage',
  'harnessRuns',
  'harnessRun',
]);

interface Operation {
  query?: string;
  variables?: Record<string, unknown>;
}

/** The fixture key of the operation's (first) Query field. */
function keyOf(field: string, variables: Record<string, unknown>): string {
  if (field === 'ingestionCell')
    return `${field}:${String(variables['dataset'])}/${String(variables['date'])}`;
  if (field === 'run' || field === 'runItems' || field === 'harnessRun')
    return `${field}:${String(variables['runId'])}`;
  return field;
}

export async function mockAdminApi(page: Page, overrides: AdminFixtures = {}): Promise<void> {
  const answers: AdminFixtures = { harnessRuns: [], ...ADMIN_FIXTURES, ...overrides };
  await page.route('**/api/graphql', async (route: Route) => {
    const operation = (route.request().postDataJSON() ?? {}) as Operation;
    const field = /\{\s*(\w+)/.exec(operation.query ?? '')?.[1] ?? '';
    if (/query\s+StatusStrip\b/.test(operation.query ?? '') && operation.variables?.['admin']) {
      // The status strip's one read: an admin adds the newest nightly run and the grid.
      const failing = answers['nightlyRuns'] === FAIL || answers['completeness'] === FAIL;
      await route.fulfill({
        json: failing
          ? {
              data: null,
              errors: [{ message: 'store unavailable', extensions: { code: 'INTERNAL' } }],
            }
          : {
              data: {
                nightlyRuns: answers['nightlyRuns'] ?? [],
                completeness: answers['completeness'] ?? null,
              },
            },
      });
      return;
    }
    if (!FIELDS.has(field)) {
      await route.fallback();
      return;
    }
    const answer = answers[keyOf(field, operation.variables ?? {})];
    await route.fulfill({
      json:
        answer === FAIL
          ? {
              data: null,
              errors: [{ message: 'store unavailable', extensions: { code: 'INTERNAL' } }],
            }
          : { data: { [field]: answer ?? null } },
    });
  });
}

/**
 * The Guide's batched read answers no entry (`Query.guideEntries`): for an Admin spec that does
 * not mock Explore, whose help buttons would otherwise reach the network. Register it before
 * `mockAdminApi`; `mockApi` has the real answers instead.
 */
export async function mockNoGuideEntries(page: Page): Promise<void> {
  await page.route('**/api/graphql', async (route: Route) => {
    const operation = (route.request().postDataJSON() ?? {}) as Operation;
    if (!/query\s+GuideEntries\b/.test(operation.query ?? '')) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      json: { data: { guideEntries: { indicators: [], episodes: [], terms: [], startPages: [] } } },
    });
  });
}
