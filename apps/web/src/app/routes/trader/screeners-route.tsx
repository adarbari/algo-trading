/**
 * Trader > Screeners: the list (`/screeners`), a new screener (`/screeners/new`), a screener's
 * results (`/screeners/$id`, where the list opens) and its Builder (`/screeners/$id/edit`).
 * Tickers open in Explore.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { NewScreenerPage, ScreenerBuilderPage } from '@/pages/screener-builder';
import { ScreenerResultsPage } from '@/pages/screener-results';
import { ScreenersPage } from '@/pages/trader-screeners';

import { traderRoute } from './layout-route';

export const screenersRoute = createRoute({ getParentRoute: () => traderRoute, path: 'screeners' });

function ScreenersIndex() {
  const navigate = useNavigate();
  return (
    <ScreenersPage
      onNew={() => void navigate({ to: '/screeners/new' })}
      onOpen={(id) => void navigate({ to: '/screeners/$id', params: { id } })}
      onEdit={(id) => void navigate({ to: '/screeners/$id/edit', params: { id } })}
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
    />
  );
}

function EditScreener() {
  const { id } = editRoute.useParams();
  const navigate = useNavigate();
  return (
    <ScreenerBuilderPage
      id={id}
      onOpenTicker={(symbol) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })
      }
    />
  );
}

const indexRoute = createRoute({
  getParentRoute: () => screenersRoute,
  path: '/',
  component: ScreenersIndex,
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
