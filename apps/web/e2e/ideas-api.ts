/**
 * Playwright route mock for the Ideas page: the `IdeasPage` GraphQL operation (POST
 * /api/graphql) answers from the fixture (e2e/fixtures/ideas/ideas-page.json, shaped from the
 * schema's `Ideas`) narrowed by the request's `filters` the way the server does for the two
 * filters it defines (a decision pick and an agreeing-screeners range) and served with `facets`;
 * the `FilterSet` operation answers with those two definitions; the `EdgeDesk` operation (the followed edges' signals) answers with no
 * followed edge unless a test gives it a desk; any other operation falls through to the other
 * areas' mocks.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

const FIXTURE: unknown = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/ideas/ideas-page.json', import.meta.url)), 'utf8'),
);

const DOLLAR = 'rollup.option_liquidity@v1.stock_volume';

/** The `filterFeatures` answer: two catalogue fields the viewer may filter on. */
const FILTER_FEATURES = {
  data: {
    filterFeatures: [
      {
        name: DOLLAR,
        label: 'stock volume',
        kind: 'RANGE',
        guide: `field:${DOLLAR}`,
        synonyms: ['liquid', 'turnover'],
      },
    ],
  },
};

const filterSet = (withFeatures: string[] | null | undefined) => ({
  data: {
    filterSet: {
      ...FILTER_SET.data.filterSet,
      filters: [
        ...FILTER_SET.data.filterSet.filters,
        ...(withFeatures ?? []).map((f) => ({
          id: `feature:${f}`,
          label: 'stock volume',
          group: 'MORE',
          kind: 'RANGE',
          guide: `field:${f}`,
          options: [],
          bins: [],
          windowUnit: null,
          unit: null,
        })),
      ],
    },
  },
});

const FILTER_SET = {
  data: {
    filterSet: {
      surface: 'ideas',
      label: 'Ideas',
      searchable: true,
      filters: [
        {
          id: 'decision',
          label: 'Decision',
          group: 'SETUP',
          kind: 'PICK',
          guide: 'term:filter_decision',
          options: [
            { value: 'QUALIFIED', label: 'Qualified' },
            { value: 'EVENT_RISK', label: 'Event risk' },
            { value: 'LIQUIDITY_RISK', label: 'Liquidity risk' },
          ],
          bins: [],
          windowUnit: null,
          unit: null,
        },
        {
          id: 'agreeing',
          label: 'Agreeing screeners',
          group: 'SETUP',
          kind: 'RANGE',
          guide: 'term:filter_agreeing',
          options: [],
          bins: [1, 2, 3],
          windowUnit: null,
          unit: null,
        },
      ],
    },
  },
};

interface Item {
  best: { decision: string };
  pickedBy: unknown[];
}
interface Input {
  id: string;
  values: string[];
  min: number | null;
  max: number | null;
  active: boolean;
}

const passes = (item: Item, f: Input): boolean => {
  if (f.id.startsWith('feature:')) return true; // the fixture holds no catalogue values
  if (f.id === 'decision') return f.values.includes(item.best.decision);
  const n = item.pickedBy.length;
  return (f.min === null || n >= f.min) && (f.max === null || n <= f.max);
};

/** The fixture as the server serves it under `filters`: the rows that pass, and the counts. */
function served(filters: Input[] | null): unknown {
  const fixture = FIXTURE as { data: { ideas: { items: Item[]; total: number } } };
  const all = fixture.data.ideas.items;
  const active = (filters ?? []).filter((f) => f.active);
  const passing = (others: Input[]) => all.filter((i) => others.every((f) => passes(i, f)));
  const items = passing(active);
  const facets = {
    total: all.length,
    matched: items.length,
    items: (filters ?? []).map((f) => ({
      id: f.id,
      active: f.active,
      removes: f.active ? passing(active.filter((o) => o !== f)).length - items.length : null,
      unknown: 0,
      options: [],
      bins: [],
    })),
  };
  return {
    data: {
      ideas: {
        ...fixture.data.ideas,
        items,
        total: items.length,
        hasMore: false,
        nextCursor: null,
        facets,
      },
    },
  };
}

/** The signals of a user who follows nothing (the Ideas page then shows one line). */
export const NO_EDGE_DESK = { data: { edgeDesk: null } };

export async function mockIdeasApi(page: Page, edgeDesk: unknown = NO_EDGE_DESK): Promise<void> {
  await page.route('**/api/graphql', async (route: Route) => {
    const body = route.request().postDataJSON() as {
      query?: string;
      variables?: { filters?: Input[] | null; withFeatures?: string[] | null; surface?: string };
    } | null;
    if (/query\s+EdgeDesk\b/.test(body?.query ?? '')) {
      await route.fulfill({ json: edgeDesk });
      return;
    }
    if (/query\s+FilterSet\b/.test(body?.query ?? '') && body?.variables?.surface === 'ideas') {
      await route.fulfill({ json: filterSet(body.variables.withFeatures) });
      return;
    }
    if (/query\s+FilterFeatures\b/.test(body?.query ?? '')) {
      await route.fulfill({ json: FILTER_FEATURES });
      return;
    }
    if (!/query\s+IdeasPage\b/.test(body?.query ?? '')) {
      await route.fallback();
      return;
    }
    await route.fulfill({ json: served(body?.variables?.filters ?? null) });
  });
}
