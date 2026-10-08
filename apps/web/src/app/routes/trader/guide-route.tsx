/**
 * The Guide (ADR 0051): `/guide` (home), `/guide/fields` (the field index; `view`, `theme` and
 * `intent` in the search params, so every view is a link) and `/guide/fields/$name` (a field's
 * page; the name is the catalogue name), `/guide/playbooks` and `/guide/playbooks/$id` (a site
 * preset's playbook; its buttons open that screener's results and Builder) and
 * `/guide/situations` and `/guide/situations/$slug`. No role gating: it sits in the trader layout, which
 * every registered user may enter; the top bar's Guide link shows in both workspaces.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { parseFieldsSearch } from '@/entities/guide';
import {
  GuideFieldPage,
  GuideFieldsPage,
  GuideHomePage,
  GuidePlaybookPage,
  GuidePlaybooksPage,
  GuideSituationPage,
  GuideSituationsPage,
} from '@/pages/guide';

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

const playbooksRoute = createRoute({
  getParentRoute: () => guideRoute,
  path: 'playbooks',
  component: GuidePlaybooksPage,
});

function PlaybookRoute() {
  const { id } = playbookRoute.useParams();
  const navigate = useNavigate();
  return (
    <GuidePlaybookPage
      id={id}
      onSeeHits={() => void navigate({ to: '/screeners/$id', params: { id } })}
      onOpenBuilder={() => void navigate({ to: '/screeners/$id/edit', params: { id } })}
    />
  );
}

const playbookRoute = createRoute({
  getParentRoute: () => guideRoute,
  path: 'playbooks/$id',
  component: PlaybookRoute,
});

const situationsRoute = createRoute({
  getParentRoute: () => guideRoute,
  path: 'situations',
  component: GuideSituationsPage,
});

function SituationRoute() {
  const { slug } = situationRoute.useParams();
  return <GuideSituationPage slug={slug} />;
}

const situationRoute = createRoute({
  getParentRoute: () => guideRoute,
  path: 'situations/$slug',
  component: SituationRoute,
});

export const guideRoutes = guideRoute.addChildren([
  homeRoute,
  fieldsRoute,
  fieldRoute,
  playbooksRoute,
  playbookRoute,
  situationsRoute,
  situationRoute,
]);
