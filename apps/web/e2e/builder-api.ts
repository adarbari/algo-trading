/**
 * Playwright route mock for the Screeners pages (list, new, Builder): the configs list, one
 * screen's detail / versions, draft save and discard, finalise, schedule, copy, rebase, the live
 * preview and the formula check / save, answering from e2e/fixtures/builder/ (shaped from the
 * API's schemas) with a little state so a flow reads back what it wrote. Every call it records
 * is exposed for assertions. Anything else falls through to the other mocks.
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
  schedules: { id: string; schedule: unknown }[];
  copies: { id: string; preset: string }[];
  rebased: string[];
  checks: string[];
  features: Json[];
  /** The query of every GET /screens/{id}/table. */
  tables: Record<string, string>[];
  /** Every PUT of a screener view. */
  views: { id: string; view: Json }[];
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
    schedules: [],
    copies: [],
    rebased: [],
    checks: [],
    features: [],
    tables: [],
    views: [],
    runs: [],
  };
  const details: Record<string, Json> = Object.fromEntries(
    Object.entries(DETAILS).map(([id, detail]) => [id, structuredClone(detail)]),
  );

  const saved: Record<string, Json> = {}; // the views a flow saved, read back by the next GET
  const ran = new Set<string>(); // the screeners whose requested run has finished
  let polls = 0;
  const detailOf = (id: string): Json | null => details[id] ?? null;
  // Your screens: one finalised with a working copy, one draft only; copies and new drafts join.
  const own = new Set(['my-vrp']);
  const listing = (): Json[] => [
    {
      screener_id: 'idea-draft',
      status: 'DRAFT',
      latest: null,
      has_draft: true,
      schedule: null,
      preset_id: 'vrp_scanner',
    },
    ...[...own].map((id) => {
      const detail = details[id] ?? {};
      const versions = (detail['versions'] as number[] | undefined) ?? [];
      const preset = detail['preset'] as { preset_id: string } | null | undefined;
      return {
        screener_id: id,
        status: versions.length > 0 ? 'FINAL' : 'DRAFT',
        latest: (detail['latest'] as number | null | undefined) ?? null,
        has_draft: detail['draft'] != null,
        schedule: (detail['schedule'] as string | null | undefined) ?? null,
        preset_id: preset?.preset_id ?? null,
      };
    }),
  ];

  await page.route('**/api/**', async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, '');
    const method = request.method();
    const body = (): Json => (request.postDataJSON() ?? {}) as Json;
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data });

    if (path === '/configs' && method === 'GET') return json(CONFIGS);
    if (path === '/screeners' && method === 'GET') return json(listing());
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
      if (method === 'PUT') {
        const view = body();
        mock.views.push({ id, view });
        saved[id] = { screener_id: id, saved: true, ...view };
        return json(saved[id]);
      }
      return json(saved[id] ?? { ...fixture('view.json'), screener_id: id });
    }
    const match = /^\/screeners\/([^/]+)(?:\/(\w+))?$/.exec(path);
    if (!match) return route.fallback();
    const id = decodeURIComponent(match[1] ?? '');
    const part = match[2] ?? '';

    if (part === '' && method === 'GET') {
      const detail = detailOf(id);
      return detail ? json(detail) : json({ detail: `no screen ${id}` }, 404);
    }
    if (part === 'versions' && method === 'GET') {
      const detail = detailOf(id);
      const versions = (detail?.['versions'] as number[] | undefined) ?? [];
      return json(
        versions.map((version) => ({
          version,
          document: { id, extends: 'vrp_scanner@1', version, criteria: { iv30: { value: 0.4 } } },
        })),
      );
    }
    if (part === 'draft' && method === 'PUT') {
      const document = body()['document'] as Json;
      mock.drafts.push({ id, document });
      own.add(id);
      const detail = detailOf(id) ?? {
        screener_id: id,
        user: 'abhinav',
        versions: [],
        latest: null,
        schedule: null,
        preset: null,
        working: { criteria: {} },
      };
      details[id] = { ...detail, draft: document, draft_error: null };
      return json({ screener_id: id, document });
    }
    if (part === 'draft' && method === 'DELETE') {
      mock.discarded.push(id);
      const detail = detailOf(id);
      if (detail) details[id] = { ...detail, draft: null, draft_error: null };
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
    if (part === 'schedule' && method === 'PUT') {
      const schedule = body()['schedule'];
      mock.schedules.push({ id, schedule });
      details[id] = { ...(detailOf(id) ?? {}), schedule };
      return json({ screener_id: id, schedule });
    }
    if (part === 'rebase' && method === 'POST') {
      mock.rebased.push(id);
      const detail = detailOf(id) ?? {};
      const draft = { id, extends: 'vrp_scanner@2', criteria: { iv30: { value: 0.45 } } };
      details[id] = {
        ...detail,
        draft,
        preset: { preset_id: 'vrp_scanner', pinned: 2, current: 2, rebase_available: false },
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
        screener_id: id,
        draft,
        preset: { preset_id: preset, pinned: 2, current: 2, rebase_available: false },
      };
      return json({ screener_id: id, document: draft }, 201);
    }
    return route.fallback();
  });
  return mock;
}
