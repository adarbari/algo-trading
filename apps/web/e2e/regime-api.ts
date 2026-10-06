/**
 * Playwright route mock for the market regime: the `Regime` and `RegimeBands` GraphQL
 * operations (POST /api/graphql) answer from fixtures recorded from the real API on the golden
 * store (e2e/fixtures/regime/): the regime is UNKNOWN (`NOT_IN_CATALOGUE`, the RG3 groups do not
 * exist yet) with its eight indicator cards, and the band history is one UNKNOWN band. Any other
 * operation falls through to the other areas' mocks. `mockRegimeComputed` serves the same
 * regime as a computed CAUTION one (the RG3 groups are not stored yet) and `mockExplain` the
 * `POST /regime/explain` of an API with a text model (the empty probe answers 400, the
 * question an explanation) or without one (503): the explain button's availability.
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

/** The regime fixture as a computed one, so the page offers to explain it. */
export async function mockRegimeComputed(page: Page): Promise<void> {
  const regime = (REGIME as { data: { regime: Record<string, unknown> } }).data.regime;
  const computed = {
    data: {
      regime: { ...regime, label: 'CAUTION', headline: '2 of 5 slow-moving warning signs are on.' },
    },
  };
  await page.route('**/api/graphql', async (route: Route) => {
    const query = (route.request().postDataJSON() as { query?: string } | null)?.query ?? '';
    if (/query\s+Regime\b/.test(query)) await route.fulfill({ json: computed });
    else await route.fallback();
  });
}

export const EXPLANATION = {
  text: 'Clouds are building: two slow warning signs are on.',
  citations: [{ title: 'FRED: T10Y3M', url: 'https://fred.stlouisfed.org/series/T10Y3M' }],
  checked: true,
  note: null,
  cached: false,
};

/** `POST /api/regime/explain` of an API with a text model (`on`) or without one. */
export async function mockExplain(page: Page, on: boolean): Promise<void> {
  await page.route('**/api/regime/explain', async (route: Route) => {
    const body = route.request().postDataJSON() as { question: string | null; card: string | null };
    if (!on) {
      await route.fulfill({
        status: 503,
        json: { detail: 'the text model is off: enable it in config/site/llm.toml (ADR 0041)' },
      });
    } else if (body.question === null && body.card === null) {
      await route.fulfill({ status: 400, json: { detail: 'ask one of question or card' } });
    } else {
      await route.fulfill({ json: EXPLANATION });
    }
  });
}
