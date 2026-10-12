/**
 * Playwright route mock for the Screeners pages (list, new, Builder, results): the GraphQL
 * reads (the screener configs, the user's screens, one screen's detail / versions, a
 * screener's results, a saved table view), draft save and discard, finalise, copy, rebase,
 * views saved and removed, a run on request, the live preview and the formula check / save,
 * answering from e2e/fixtures/builder/ (shaped from the API's schemas) with a little state so a
 * flow reads back what it wrote. Every call it records is exposed for assertions. Anything else
 * (other GraphQL operations too) falls through to the other mocks. `mockDescribeApi` adds
 * "Describe it" (draft-from-text, ADR 0041 and ADR 0066) on top of it.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

type Json = Record<string, unknown>;

const fixture = (name: string): Json =>
  JSON.parse(
    readFileSync(fileURLToPath(new URL(`./fixtures/builder/${name}`, import.meta.url)), 'utf8'),
  ) as Json;

const CONFIGS = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/builder/configs.json', import.meta.url)), 'utf8'),
) as Json[];

const DETAILS: Record<string, Json> = {
  'my-vrp': fixture('detail-my-vrp.json'),
  vrp_scanner: fixture('detail-vrp-scanner.json'),
  fresh: fixture('detail-fresh.json'),
};

export interface BuilderMockOptions {
  /** Answer POST /screeners/preview with a 400 naming this criterion. */
  failPreviewOn?: string;
}

/** What the page sent, in order (for assertions). */
export interface BuilderMock {
  drafts: { id: string; document: Json }[];
  previews: Json[];
  discarded: string[];
  finalised: string[];
  copies: { id: string; preset: string }[];
  rebased: string[];
  checks: string[];
  features: Json[];
  /** The variables of every `ScreenerResults` read. */
  tables: Json[];
  /** Every PUT of a screener view (`name`: null for the default view). */
  views: { id: string; name: string | null; view: Json }[];
  /** Every DELETE of a named view. */
  removedViews: string[];
  /** The screeners whose run was requested (POST /screens/{id}/run). */
  runs: string[];
}

export async function mockBuilderApi(
  page: Page,
  options: BuilderMockOptions = {},
): Promise<BuilderMock> {
  const mock: BuilderMock = {
    drafts: [],
    previews: [],
    discarded: [],
    finalised: [],
    copies: [],
    rebased: [],
    checks: [],
    features: [],
    tables: [],
    views: [],
    removedViews: [],
    runs: [],
  };
  const details: Record<string, Json> = Object.fromEntries(
    Object.entries(DETAILS).map(([id, detail]) => [id, structuredClone(detail)]),
  );

  const saved: Record<string, Json> = {}; // the views a flow saved ('id|name'), read back by GraphQL
  const namesOf = (id: string): string[] =>
    Object.keys(saved)
      .filter((key) => key.startsWith(`${id}|`) && key !== `${id}|`)
      .map((key) => key.slice(id.length + 1))
      .sort();
  const ran = new Set<string>(); // the screeners whose requested run has finished
  let polls = 0;
  let lastRun = ''; // the screener whose run was last requested (the job poll names only the job)
  const detailOf = (id: string): Json | null => details[id] ?? null;
  // Your screens: one finalised with a working copy, one draft only; copies and new drafts join.
  const own = new Set(['my-vrp']);
  const listing = (): Json[] => [
    {
      screenerId: 'idea-draft',
      status: 'DRAFT',
      latest: null,
      hasDraft: true,
      presetId: 'vrp_scanner',
    },
    ...[...own].map((id) => {
      const detail = details[id] ?? {};
      const versions = (detail['versions'] as number[] | undefined) ?? [];
      const preset = detail['preset'] as { presetId: string } | null | undefined;
      return {
        screenerId: id,
        status: versions.length > 0 ? 'FINAL' : 'DRAFT',
        latest: (detail['latest'] as number | null | undefined) ?? null,
        hasDraft: detail['draft'] != null,
        presetId: preset?.presetId ?? null,
      };
    }),
  ];
  const versionsOf = (id: string): Json[] =>
    ((detailOf(id)?.['versions'] as number[] | undefined) ?? []).map((version) => ({
      version,
      document: { id, extends: 'vrp_scanner@1', version, criteria: { iv30: { value: 0.4 } } },
    }));
  /** The screens' GraphQL reads, by operation name; null: not one of them. */
  const graphqlAnswer = (operation: { query?: string; variables?: Json }): Json | null => {
    const name = /query\s+(\w+)/.exec(operation.query ?? '')?.[1];
    const raw = operation.variables?.['id'];
    const id = typeof raw === 'string' ? raw : '';
    if (name === 'ScreenerConfigs') return { configs: CONFIGS };
    if (name === 'MyScreens') return { myScreens: listing() };
    if (name === 'ScreenerRuns') {
      const ran12 = {
        runId: 'r1',
        session: '2026-10-07',
        picked: 12,
        paused: 0,
        decisions: [
          { decision: 'QUALIFIED', count: 12 },
          { decision: 'REJECT', count: 400 },
        ],
        changes: [
          { change: 'new', count: 3 },
          { change: 'dropped', count: 1 },
        ],
      };
      const notRun = { kindText: 'not run for this session' };
      const criteria = [
        { id: 'iv_hv_ratio', field: 'feature.iv_hv_ratio', mode: 'soft', op: 'gte', value: 1.25 },
      ];
      const pickHistory = [
        { session: '2026-10-06', picked: 10 },
        { session: '2026-10-07', picked: 12 },
      ];
      return {
        session: { date: '2026-10-07' },
        screeners: [
          {
            id: 'vrp_scanner',
            name: 'vrp_scanner',
            criteria,
            pickHistory,
            notRun: null,
            latestRun: ran12,
          },
          ...[...own, 'idea-draft'].map((id) => ({
            id,
            name: id,
            criteria,
            pickHistory,
            notRun,
            latestRun: null,
          })),
        ],
      };
    }
    if (name === 'ScreenDetail') return { screenDetail: detailOf(id) };
    if (name === 'ScreenVersions') return { screenVersions: versionsOf(id) };
    if (name === 'ScreenerPicks') {
      const results = fixture('results.json') as {
        screener: { latestRun: { results: { results: { instrumentId: string }[] } } };
      };
      const ids = results.screener.latestRun.results.results.map((r) => r.instrumentId);
      return id === 'vrp_scanner' || ran.has(id)
        ? {
            screener: {
              id,
              notRun: null,
              latestRun: { runId: 'r1', pickIds: { total: ids.length, instrumentIds: ids } },
            },
          }
        : {
            screener: {
              id,
              notRun: {
                code: 'NOT_RUN',
                kind: 'NOT_RUN',
                guideTerm: 'not_run',
                kindText: 'not run for this session',
                cause: null,
              },
              latestRun: null,
            },
          };
    }
    if (name === 'ScreenerResults') {
      mock.tables.push(operation.variables ?? {});
      const results = fixture('results.json') as { screener: Json };
      const screener = { ...results.screener, id };
      return id === 'vrp_scanner' || ran.has(id)
        ? { ...results, screener }
        : {
            ...results,
            screener: {
              ...screener,
              latestRun: null,
              notRun: {
                code: 'NOT_RUN',
                kind: 'NOT_RUN',
                guideTerm: 'not_run',
                kindText: 'not run for this session',
                cause: null,
              },
            },
          };
    }
    if (name === 'TableView') {
      const raw = operation.variables?.['scope'];
      const scope = typeof raw === 'string' ? raw : '';
      const viewId = scope.replace(/^screener:/, '');
      const viewName = (operation.variables?.['name'] as string | null | undefined) ?? null;
      const key = `${viewId}|${viewName ?? ''}`;
      return {
        view: {
          ...(saved[key] ?? { ...fixture('view.json'), scope, name: viewName }),
          names: namesOf(viewId),
        },
      };
    }
    return null;
  };

  await page.route('**/api/**', async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, '');
    const method = request.method();
    const body = (): Json => (request.postDataJSON() ?? {}) as Json;
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data });

    if (path === '/graphql' && method === 'POST') {
      const data = graphqlAnswer(body());
      return data === null ? route.fallback() : json({ data });
    }
    if (path === '/screeners/preview' && method === 'POST') {
      const spec = body()['spec'] as Json;
      mock.previews.push(spec);
      if (options.failPreviewOn) {
        return json(
          {
            detail: `${String(spec['id'])}.criteria.${options.failPreviewOn}.field: unknown field 'rollup.nope@v1.x'`,
          },
          400,
        );
      }
      return json(fixture('preview.json'));
    }
    if (path === '/features/check' && method === 'POST') {
      const expr = String(body()['expr']);
      mock.checks.push(expr);
      if (expr.includes('nope')) {
        return json({ detail: "1:1: unknown feature 'nope'" }, 400);
      }
      return json({ ...fixture('check.json'), expr });
    }
    if (path === '/features/user' && method === 'POST') {
      const feature = body();
      mock.features.push(feature);
      return json(
        {
          name: feature['name'],
          field: `feature.${String(feature['name'])}`,
          theme: 'builder',
          dtype: feature['dtype'],
          kind: 'expression',
          inputs: [],
        },
        201,
      );
    }
    const view = (state: string) => ({
      job_id: 'job-screen-1',
      kind: 'screen',
      state,
      user: 'ann',
      session: '2026-10-02',
      run_id: state === 'complete' ? 'run-1' : null,
      exploratory: null,
      error: null,
    });
    const run = /^\/screens\/([^/]+)\/run$/.exec(path);
    if (run && method === 'POST') {
      lastRun = decodeURIComponent(run[1] ?? '');
      mock.runs.push(lastRun);
      polls = 0;
      return route.fulfill({
        status: 202,
        json: { ...view('running'), config_id: lastRun, state: 'running' },
      });
    }
    if (/^\/jobs\/[^/]+$/.test(path) && method === 'GET') {
      polls += 1; // the first poll still sees it running
      if (polls > 1) ran.add(lastRun);
      return json(view(polls > 1 ? 'complete' : 'running'));
    }
    const viewOf = /^\/preferences\/views\/screener:([^/]+)\/view$/.exec(decodeURIComponent(path));
    if (viewOf) {
      const id = viewOf[1] ?? '';
      const name = url.searchParams.get('name');
      const key = `${id}|${name ?? ''}`;
      if (method === 'PUT') {
        const view = body();
        mock.views.push({ id, name, view });
        const { narrow_columns: narrowColumns = [], ...rest } = view;
        saved[key] = { scope: `screener:${id}`, name, saved: true, ...rest, narrowColumns };
        return json({ ...saved[key], narrow_columns: narrowColumns, names: namesOf(id) });
      }
      if (method === 'DELETE') {
        mock.removedViews.push(String(name));
        Reflect.deleteProperty(saved, key);
        return json({ names: namesOf(id) });
      }
    }
    const match = /^\/screeners\/([^/]+)(?:\/(\w+))?$/.exec(path);
    if (!match) return route.fallback();
    const id = decodeURIComponent(match[1] ?? '');
    const part = match[2] ?? '';

    if (part === 'draft' && method === 'PUT') {
      const document = body()['document'] as Json;
      mock.drafts.push({ id, document });
      own.add(id);
      const detail = detailOf(id) ?? {
        screenerId: id,
        user: 'abhinav',
        versions: [],
        latest: null,
        preset: null,
        working: { criteria: {} },
      };
      details[id] = { ...detail, draft: document, draftError: null };
      return json({ screener_id: id, document });
    }
    if (part === 'draft' && method === 'DELETE') {
      mock.discarded.push(id);
      const detail = detailOf(id);
      if (detail) details[id] = { ...detail, draft: null, draftError: null };
      if (((detail?.['versions'] as number[] | undefined) ?? []).length === 0) own.delete(id);
      return route.fulfill({ status: 204 });
    }
    if (part === 'finalise' && method === 'POST') {
      mock.finalised.push(id);
      const detail = detailOf(id) ?? {};
      const version = ((detail['latest'] as number | null) ?? 0) + 1;
      details[id] = {
        ...detail,
        draft: null,
        versions: [...((detail['versions'] as number[] | undefined) ?? []), version],
        latest: version,
      };
      return json({ screener_id: id, version, hash: 'h-new' });
    }
    if (part === 'rebase' && method === 'POST') {
      mock.rebased.push(id);
      const detail = detailOf(id) ?? {};
      const draft = { id, extends: 'vrp_scanner@2', criteria: { iv30: { value: 0.45 } } };
      details[id] = {
        ...detail,
        draft,
        preset: { presetId: 'vrp_scanner', pinned: 2, current: 2, rebaseAvailable: false },
      };
      return json({ screener_id: id, document: draft });
    }
    if (part === 'copy' && method === 'POST') {
      const preset = String(body()['preset']);
      mock.copies.push({ id, preset });
      own.add(id);
      const draft = { id, extends: `${preset}@2` };
      details[id] = {
        ...structuredClone(DETAILS['vrp_scanner'] ?? {}),
        screenerId: id,
        draft,
        preset: { presetId: preset, pinned: 2, current: 2, rebaseAvailable: false },
      };
      return json({ screener_id: id, document: draft }, 201);
    }
    return route.fallback();
  });
  return mock;
}

/*
 * Describe it: answers any sentence with one applied criterion, one proposed formula whose
 * criterion waits for the trader's decision and one suggested soft check, as explained parts (one
 * card each), and records what the page sent. Register it after
 * `mockBuilderApi` (the later route is tried first; anything else falls through to it).
 */
export const FORMULA_NAME = 'draft_iv_over_hv';
export const FORMULA_EXPR = 'rollup.iv30@v1.iv30 - rollup.price_stats@v2.hv30';

const FORMULA = {
  name: FORMULA_NAME,
  expr: FORMULA_EXPR,
  dtype: 'float32',
  unit: 'ratio',
  description: 'IV30 minus HV30',
  null_meaning: 'either volatility is missing',
  inputs: ['rollup.iv30@v1.iv30', 'rollup.price_stats@v2.hv30'],
  criterion: { field: `feature.${FORMULA_NAME}`, op: 'gte', value: 0.05, mode: 'hard' },
  fingerprint: 'fp-1',
  pending: true,
  dry_run: {
    rows: 11427,
    no_value_rate: 0.31,
    minimum: -0.4,
    maximum: 0.9,
    criterion_pass: 1204,
    session: '2026-10-02',
    sample: [
      { instrument_id: 'EQ:AAA', value: 0.12 },
      { instrument_id: 'EQ:BBB', value: -0.02 },
    ],
  },
};

export const SUGGESTION_FIELD = 'rollup.price_stats@v2.hv30';

const SUGGESTION = {
  id: 'sg1',
  criterion: { field: SUGGESTION_FIELD, op: 'lte', value: 0.8, mode: 'soft' },
  source: 'hv30',
  why: 'A very high realised volatility makes the premium easy to lose',
};

const PART = {
  start: 0,
  end: 0,
  reading_source: 'model',
  origin: 'words',
  dropped: [],
  missing: [],
};

const PARTS = [
  {
    ...PART,
    id: 'p1',
    words: 'IV above HV',
    reading: 'implied volatility higher than realised volatility',
    kind: 'formula',
    criteria: [],
    formulas: [FORMULA_NAME],
    unresolved: [],
    suggestions: [],
  },
  {
    ...PART,
    id: 'p2',
    words: 'and above 50%',
    reading: 'implied volatility at least 0.5',
    kind: 'applied',
    criteria: ['iv30'],
    formulas: [],
    unresolved: [],
    suggestions: ['sg1'],
  },
];

export interface DescribeMock {
  /** The body of every draft-from-text POST. */
  sentences: Json[];
}

export async function mockDescribeApi(page: Page): Promise<DescribeMock> {
  const mock: DescribeMock = { sentences: [] };
  await page.route('**/api/screeners/*/draft-from-text', async (route: Route) => {
    const body = (route.request().postDataJSON() ?? {}) as Json;
    mock.sentences.push(body);
    const id = decodeURIComponent(/screeners\/([^/]+)\//.exec(route.request().url())?.[1] ?? '');
    await route.fulfill({
      status: 200,
      json: {
        screener_id: id,
        document: {
          id,
          criteria: {
            iv30: { field: 'rollup.iv30@v1.iv30', op: 'gte', value: 0.5, mode: 'hard' },
          },
        },
        dropped: [],
        notes: [],
        formulas: [FORMULA],
        suggestions: [SUGGESTION],
        sentence: typeof body['text'] === 'string' ? body['text'] : '',
        parts: PARTS,
        draft_session_id: 'sess-e2e',
      },
    });
  });
  return mock;
}
