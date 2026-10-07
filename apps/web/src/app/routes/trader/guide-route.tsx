/**
 * The Guide (ADR 0051): `/guide` (home), `/guide/fields` (the field index; `view`, `theme` and
 * `intent` in the search params, so every view is a link) and `/guide/fields/$name` (a field's
 * page; the name is the catalogue name). No role gating: it sits in the trader layout, which
 * every registered user may enter; the top bar's Guide link shows in both workspaces.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { parseFieldsSearch } from '@/entities/guide';
import { GuideFieldPage, GuideFieldsPage, GuideHomePage } from '@/pages/guide';

import { traderRoute } from './layout-route';

export const guideRoute = createRoute({ getParentRoute: () => traderRoute, path: 'guide' });

const homeRoute = createRoute({
  getParentRoute: () => guideRoute,
  path: '/',
  component: GuideHomePage,
});

function FieldsRoute() {
  const search = fieldsRoute.useSearch();
  const navigate = useNavigate({ from: fieldsRoute.fullPath });
  return (
    <GuideFieldsPage
      {...search}
      onViewChange={(view) =>
        void navigate({ search: view === 'theme' ? {} : { view }, replace: true })
      }
    />
  );
}

const fieldsRoute = createRoute({
  getParentRoute: () => guideRoute,
  path: 'fields',
  validateSearch: parseFieldsSearch,
  component: FieldsRoute,
});

function FieldRoute() {
  const { name } = fieldRoute.useParams();
  const navigate = useNavigate();
  return (
    <GuideFieldPage name={name} onAddToBuilder={() => void navigate({ to: '/screeners/new' })} />
  );
}

const fieldRoute = createRoute({
  getParentRoute: () => guideRoute,
  path: 'fields/$name',
  component: FieldRoute,
});

export const guideRoutes = guideRoute.addChildren([homeRoute, fieldsRoute, fieldRoute]);
