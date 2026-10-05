/**
 * Playwright route mock for the Screeners pages (list, new, Builder): the GraphQL reads (the
 * screener configs, the user's screens, one screen's detail / versions), draft save and
 * discard, finalise, copy, rebase, the live preview and the formula check / save, answering
 * from e2e/fixtures/builder/ (shaped from the API's schemas) with a little state so a flow reads
 * back what it wrote. Every call it records is exposed for assertions. Anything else (other
 * GraphQL operations too) falls through to the other mocks.
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
  /** The query of every GET /screens/{id}/table. */
  tables: Record<string, string>[];
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

  const saved: Record<string, Json> = {}; // the views a flow saved ('id|name'), read back by GET
  const namesOf = (id: string): string[] =>
    Object.keys(saved)
      .filter((key) => key.startsWith(`${id}|`) && key !== `${id}|`)
      .map((key) => key.slice(id.length + 1))
      .sort();
  const ran = new Set<string>(); // the screeners whose requested run has finished
  let polls = 0;
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
    if (name === 'ScreenDetail') return { screenDetail: detailOf(id) };
    if (name === 'ScreenVersions') return { screenVersions: versionsOf(id) };
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
    const table = /^\/screens\/([^/]+)\/table$/.exec(path);
    if (table && method === 'GET') {
      mock.tables.push(Object.fromEntries(url.searchParams));
      const id = decodeURIComponent(table[1] ?? '');
      return id === 'vrp_scanner' || ran.has(id)
        ? json({ ...fixture('table.json'), config_id: id })
        : json({ detail: `no results of ${id} stored` }, 404);
    }
    const run = /^\/screens\/([^/]+)\/run(?:\/([^/]+))?$/.exec(path);
    if (run) {
      const id = decodeURIComponent(run[1] ?? '');
      const view = (state: string) => ({
        state,
        config_id: id,
        session: '2026-10-02',
        job_id: 'job-screen-1',
        run_id: state === 'complete' ? 'run-1' : null,
        error: null,
      });
      if (method === 'POST') {
        mock.runs.push(id);
        polls = 0;
        return route.fulfill({ status: 202, json: view('running') });
      }
      polls += 1; // the first poll still sees it running
      if (polls > 1) ran.add(id);
      return json(view(polls > 1 ? 'complete' : 'running'));
    }
    const viewOf = /^\/preferences\/screeners\/([^/]+)\/view$/.exec(path);
    if (viewOf) {
      const id = decodeURIComponent(viewOf[1] ?? '');
      const name = url.searchParams.get('name');
      const key = `${id}|${name ?? ''}`;
      if (method === 'PUT') {
        const view = body();
        mock.views.push({ id, name, view });
        saved[key] = { screener_id: id, name, saved: true, ...view };
        return json({ ...saved[key], names: namesOf(id) });
      }
      if (method === 'DELETE') {
        mock.removedViews.push(String(name));
        Reflect.deleteProperty(saved, key);
        return json({ names: namesOf(id) });
      }
      return json({
        ...(saved[key] ?? { ...fixture('view.json'), screener_id: id, name }),
        names: namesOf(id),
      });
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
