/**
 * Playwright route mock for the market regime: the `Regime` and `RegimeBands` GraphQL
 * operations (POST /api/graphql) answer from fixtures recorded from the real API on the golden
 * store (e2e/fixtures/regime/): the regime is UNKNOWN (`NOT_IN_CATALOGUE`, the RG3 groups do not
 * exist yet) with its eight indicator cards, and the band history is one UNKNOWN band. Any other
 * operation falls through to the other areas' mocks.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

const fixture = (name: string): unknown =>
  JSON.parse(
    readFileSync(fileURLToPath(new URL(`./fixtures/regime/${name}.json`, import.meta.url)), 'utf8'),
  );

const REGIME = fixture('regime');
const BANDS = fixture('regime-bands');

export async function mockRegimeApi(page: Page): Promise<void> {
  await page.route('**/api/graphql', async (route: Route) => {
    const query = (route.request().postDataJSON() as { query?: string } | null)?.query ?? '';
    if (/query\s+RegimeBands\b/.test(query)) await route.fulfill({ json: BANDS });
    else if (/query\s+Regime\b/.test(query)) await route.fulfill({ json: REGIME });
    else await route.fallback();
  });
}
