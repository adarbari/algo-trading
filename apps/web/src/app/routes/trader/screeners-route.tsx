/**
 * Trader > Screeners: the list (`/screeners`), a new screener (`/screeners/new`), a screener's
 * results (`/screeners/$id`, where the list opens) and its Builder (`/screeners/$id/edit`).
 * Tickers open in Explore.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { prefetchScreeners } from '@/entities/screen';
import { compareSearch } from '@/features/idea-compare';
import { traderRoute } from './layout-route';
import { lazyPage } from '@/shared/lib/lazy';

const NewScreenerPage = lazyPage(() => import('@/pages/screener-builder'), 'NewScreenerPage');
const ScreenerBuilderPage = lazyPage(
  () => import('@/pages/screener-builder'),
  'ScreenerBuilderPage',
);
const ScreenerResultsPage = lazyPage(
  () => import('@/pages/screener-results'),
  'ScreenerResultsPage',
);
const ScreenersPage = lazyPage(() => import('@/pages/trader-screeners'), 'ScreenersPage');

export const screenersRoute = createRoute({ getParentRoute: () => traderRoute, path: 'screeners' });

function ScreenersIndex() {
  const navigate = useNavigate();
  return (
    <ScreenersPage
      onNew={() => void navigate({ to: '/screeners/new' })}
      onOpen={(id) => void navigate({ to: '/screeners/$id', params: { id } })}
      onEdit={(id) => void navigate({ to: '/screeners/$id/edit', params: { id } })}
      onOpenTicker={(symbol, via) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol, via } })
      }
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
    />
  );
}

function NewScreener() {
  const navigate = useNavigate();
  return (
    <NewScreenerPage
      onCancel={() => void navigate({ to: '/screeners' })}
      onCreated={(id) => void navigate({ to: '/screeners/$id/edit', params: { id } })}
    />
  );
}

function ScreenerResultsRoute() {
  const { id } = resultsRoute.useParams();
  const navigate = useNavigate();
  return (
    <ScreenerResultsPage
      id={id}
      onEdit={() => void navigate({ to: '/screeners/$id/edit', params: { id } })}
      onOpenTicker={(symbol) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })
      }
      onCompare={(symbols) => {
        const search = compareSearch(symbols);
        if (search) void navigate({ to: '/explore', search });
      }}
    />
  );
}

function EditScreener() {
  const { id } = editRoute.useParams();
  const navigate = useNavigate();
  return (
    <ScreenerBuilderPage
      id={id}
      onDeleted={() => void navigate({ to: '/screeners' })}
      onOpenTicker={(symbol) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })
      }
      onOpenRegime={() => void navigate({ to: '/regime' })}
    />
  );
}

const indexRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: '/',
  component: ScreenersIndex,
  loader: ({ context }) => {
    prefetchScreeners(context.queryClient);
  },
});
const newRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: 'new',
  component: NewScreener,
});
const resultsRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: '$id',
  component: ScreenerResultsRoute,
});
const editRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: '$id/edit',
  component: EditScreener,
});

export const screenersRoutes = screenersRoute.addChildren([
  indexRoute,
  newRoute,
  resultsRoute,
  editRoute,
]);
