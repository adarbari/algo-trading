/**
 * Trader > Test (`/test`): the one flow for trying an idea on past data. Start (the four ways in
 * and the list of screeners; the filter bar's `f` and the search text `q` are its search params),
 * Guided (`/test/guided`, templates), Expert and Describe it (`/test/expert`, `/test/describe`: a
 * new draft; `/test/expert/$id`: its rules), the Result (`/test/result/$id`) and the setup builder
 * (`/test/setup`, `/test/setup/$id`). The pages after Start load lazily (`test-flow-routes.tsx`).
 * The old `/screeners` and `/edges/new`, `/edges/$id/edit` URLs redirect here (`redirects.ts`).
 * Tickers open in Explore.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { filterSearch } from '@/features/filter-bar';
import { traderRoute } from './layout-route';
import { pageRoute } from '../page-loader';
import { lazyPage } from '@/shared/lib/lazy';

// One import call for all: the entry then carries one preload file list, not five.
const flowRoutes = () => import('./test-flow-routes');
const Guided = lazyPage(flowRoutes, 'Guided');
const NewExpert = lazyPage(flowRoutes, 'NewExpert');
const NewDescribe = lazyPage(flowRoutes, 'NewDescribe');
const Expert = lazyPage(flowRoutes, 'Expert');
const Result = lazyPage(flowRoutes, 'Result');
const Setup = lazyPage(flowRoutes, 'Setup');
const TestStartPage = lazyPage(() => import('@/pages/test'), 'TestStartPage');

export const testRoute = createRoute({ getParentRoute: () => traderRoute, path: 'test' });

/** The start's search params: the filter bar's `f` and the search text `q`. */
export interface TestSearch {
  f?: string;
  q?: string;
}

export function validateTestSearch(raw: Record<string, unknown>): TestSearch {
  const { q } = raw;
  return { ...filterSearch(raw), ...(typeof q === 'string' && q.trim() ? { q } : {}) };
}

function TestIndex() {
  const navigate = useNavigate({ from: indexRoute.fullPath });
  const search = indexRoute.useSearch();
  return (
    <TestStartPage
      search={search}
      onSearchChange={(patch) =>
        void navigate({
          search: (previous) =>
            validateTestSearch(
              Object.fromEntries(
                Object.entries({ ...previous, ...patch }).filter(([, v]) => v !== undefined),
              ),
            ),
          replace: true,
        })
      }
      onChoose={(way) => {
        if (way === 'guided') void navigate({ to: '/test/guided' });
        else if (way === 'describe') void navigate({ to: '/test/describe' });
        else void navigate({ to: '/test/expert' });
      }}
      onOpen={(id) => void navigate({ to: '/test/result/$id', params: { id } })}
      onEdit={(id) => void navigate({ to: '/test/expert/$id', params: { id } })}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
    />
  );
}

const indexRoute = createRoute({
  getParentRoute: () => testRoute,
  path: '/',
  validateSearch: validateTestSearch,
  loaderDeps: ({ search }) => ({ f: search.f, q: search.q ?? '' }),
  ...pageRoute(TestStartPage, (page, client, deps: { f: string | undefined; q: string }) => {
    return page.prefetchTestStartReads(client, deps.f, deps.q);
  }),
  component: TestIndex,
});
const guidedRoute = createRoute({
  getParentRoute: () => testRoute,
  path: 'guided',
  ...pageRoute(Guided),
  component: Guided,
});
const newExpertRoute = createRoute({
  getParentRoute: () => testRoute,
  path: 'expert',
  ...pageRoute(NewExpert),
  component: NewExpert,
});
const describeRoute = createRoute({
  getParentRoute: () => testRoute,
  path: 'describe',
  ...pageRoute(NewDescribe),
  component: NewDescribe,
});
const expertRoute = createRoute({
  getParentRoute: () => testRoute,
  path: 'expert/$id',
  ...pageRoute(Expert, (m) => m.preloadExpert()),
  component: Expert,
});
const resultRoute = createRoute({
  getParentRoute: () => testRoute,
  path: 'result/$id',
  validateSearch: filterSearch,
  ...pageRoute(Result, (m) => m.preloadResult()),
  component: Result,
});
const setupNewRoute = createRoute({
  getParentRoute: () => testRoute,
  path: 'setup',
  ...pageRoute(Setup, (m) => m.preloadSetup()),
  component: Setup,
});
const setupRoute = createRoute({
  getParentRoute: () => testRoute,
  path: 'setup/$id',
  ...pageRoute(Setup, (m) => m.preloadSetup()),
  component: Setup,
});

export const testRoutes = testRoute.addChildren([
  indexRoute,
  guidedRoute,
  newExpertRoute,
  describeRoute,
  expertRoute,
  resultRoute,
  setupNewRoute,
  setupRoute,
]);
