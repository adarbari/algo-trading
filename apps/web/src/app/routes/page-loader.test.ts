/** The shared page loader and what every page route does on load (owner goal 2026-10-17). */
import { QueryClient } from '@tanstack/react-query';
import type { AnyRoute } from '@tanstack/react-router';
import { describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { pageRoute, RESTORE_WAIT_MS } from './page-loader';
import { routeTree } from './index';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn(() => new Promise(() => undefined)) };
});

type Loader = (a: { context: unknown; deps?: unknown }) => Promise<void>;

/** The query names a route's loader starts (the cache's `['gql', name, ...]` keys). */
async function started(route: AnyRoute, deps?: unknown): Promise<string[]> {
  const queryClient = new QueryClient();
  await (route.options.loader as Loader)({ context: { queryClient }, deps });
  return queryClient
    .getQueryCache()
    .getAll()
    .map((q) => String(q.queryKey[1]))
    .sort();
}

/** Every route of the tree with its full path (ids are set only once a router has the tree). */
function flatten(route: AnyRoute, parent = ''): (AnyRoute & { full: string })[] {
  const path = (route.options as { path?: string }).path ?? '';
  const full =
    path === '/' || path === '' ? parent || path : `${parent}/${path}`.replace('//', '/');
  const children = (route.children ?? []) as AnyRoute[];
  return [Object.assign(route, { full }), ...children.flatMap((c) => flatten(c, full))];
}

function find(route: AnyRoute, full: string): AnyRoute {
  const found = flatten(route).find((r) => r.full === full && r.options.loader);
  if (!found) throw new Error(`no route ${full}`);
  return found;
}

describe('pageRoute', () => {
  it('loads the page module, starts its reads and never waits for data', async () => {
    const prefetch = vi.fn();
    const page = { load: () => Promise.resolve({ x: 1 }), preload: () => Promise.resolve() };
    const options = pageRoute(page, prefetch);
    await options.loader({ context: { queryClient: new QueryClient() } });
    expect(prefetch).toHaveBeenCalledWith({ x: 1 }, expect.any(QueryClient), undefined);
    expect(options.staticData.preload).toBe(page.preload);
  });

  it('waits for the saved page cache at most RESTORE_WAIT_MS', () => {
    expect(RESTORE_WAIT_MS).toBeLessThanOrEqual(150);
  });
});

describe('every page route loads its chunk in a loader', () => {
  // Routes that render no lazy page: layouts, the index redirect, placeholders and the sign-in.
  const NO_PAGE = new Set(['', '/', '/login', '/admin', '/guide']);
  const placeholders = ['/admin/users'];

  it('has a loader and a static preload on each', () => {
    const missing = flatten(routeTree as unknown as AnyRoute)
      .filter((r) => !NO_PAGE.has(r.full) && !placeholders.includes(r.full))
      .filter((r) => r.options.component && !r.options.loader)
      .map((r) => r.full);
    expect(missing).toEqual([]);
  });
});

describe('the reads each page starts with its chunk', () => {
  const tree = routeTree as unknown as AnyRoute;
  const cases: [string, string[]][] = [
    [
      '/test',
      ['MyScreens', 'ScreenerConfigs', 'ScreenerListPage', 'ScreenerRuns', 'ScreenerTrackRecords'],
    ],
    ['/regime', ['RegimeEpisodes', 'RegimeSignals']],
    ['/calendar', ['EventCalendar', 'ScreenerConfigs']],
    ['/edges', ['EdgeDesk', 'EdgeProblems', 'EdgesPage']],
    // an edge named by the URL reads that one edge in full, not the list
    ['/edges?edge=x', ['EdgeDesk', 'EdgeDetail']],
    [
      '/admin/ingestion',
      [
        'FigiReview',
        'IngestionCompleteness',
        'LeverageReview',
        'NightlyRuns',
        'QualityChecks',
        'Verification',
      ],
    ],
    ['/admin/llm-usage', ['LlmUsage']],
    ['/admin/harness-runs', ['HarnessRuns']],
    ['/admin/screener-runs', ['AdminScreenerRuns']],
    ['/guide', ['FeatureCatalogue', 'GuideIndex']],
  ];
  it.each(cases)('%s', async (id, names) => {
    const [path, query] = id.split('?');
    const deps = query ? { edge: new URLSearchParams(query).get('edge') } : { edge: null };
    expect(await started(find(tree, path ?? id), deps)).toEqual(names);
    expect(vi.mocked(gql)).toHaveBeenCalled();
  });
});
