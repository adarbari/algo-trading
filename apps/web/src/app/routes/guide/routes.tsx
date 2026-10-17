/**
 * The Guide (ADR 0051): `/guide` (home), `/guide/fields` (the field index; `view`, `theme` and
 * `intent` in the search params, so every view is a link) and `/guide/fields/$name` (a field's
 * page; the name is the catalogue name), `/guide/playbooks` and `/guide/playbooks/$id` (a site
 * preset's playbook; its buttons open that screener's results and Builder) and
 * `/guide/situations` and `/guide/situations/$slug`, `/guide/regime`, `/guide/regime/indicators/$key`
 * and `/guide/regime/episodes/$key` (the market regime's indicators and reference falls),
 * `/guide/start` and `/guide/start/$id` (the how-tos in order) and `/guide/glossary` and
 * `/guide/glossary/$id` (the app's words A to Z). No role gating (`viewerGuard`: any registered
 * viewer) and no workspace: the layout shows the top bar of the workspace the user came from
 * (`GuideLayout`), so an admin stays in ADMIN.
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import type * as GuidePages from '@/pages/guide';

import { parseFieldsSearch } from '@/entities/guide';
import { GuideLayout } from '../../layouts';
import { viewerGuard } from '../../workspaces';
import { rootRoute } from '../root';
import { lazyPage } from '@/shared/lib/lazy';
import { pageRoute, type PageModule } from '../page-loader';

// One chunk for the Guide's pages (they share widgets), loaded when the first Guide page opens.
// One import call for every Guide page: the entry carries one preload file list, not fourteen.
const guidePages = () => import('@/pages/guide');
const GuideEpisodePage = lazyPage(guidePages, 'GuideEpisodePage');
const GuideFieldPage = lazyPage(guidePages, 'GuideFieldPage');
const GuideFieldsPage = lazyPage(guidePages, 'GuideFieldsPage');
const GuideGlossaryPage = lazyPage(guidePages, 'GuideGlossaryPage');
const GuideHomePage = lazyPage(guidePages, 'GuideHomePage');
const GuideIndicatorPage = lazyPage(guidePages, 'GuideIndicatorPage');
const GuidePlaybookPage = lazyPage(guidePages, 'GuidePlaybookPage');
const GuidePlaybooksPage = lazyPage(guidePages, 'GuidePlaybooksPage');
const GuideRegimePage = lazyPage(guidePages, 'GuideRegimePage');
const GuideSituationPage = lazyPage(guidePages, 'GuideSituationPage');
const GuideSituationsPage = lazyPage(guidePages, 'GuideSituationsPage');
const GuideStartIndexPage = lazyPage(guidePages, 'GuideStartIndexPage');
const GuideStartPage = lazyPage(guidePages, 'GuideStartPage');
const GuideTermPage = lazyPage(guidePages, 'GuideTermPage');

// Every Guide page shares one chunk and the index reads; each page preloads itself (a lazyPage
// renders unsuspended only once its own `load` ran).
const guideLoading = (page: PageModule<typeof GuidePages>) =>
  pageRoute(page, (module, client) => {
    module.prefetchGuideReads(client);
  });

export const guideRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: 'guide',
  beforeLoad: viewerGuard,
  component: GuideLayout,
});

const homeRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideHomePage),
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
  ...guideLoading(GuideFieldsPage),
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
  ...guideLoading(GuideFieldPage),
  path: 'fields/$name',
  component: FieldRoute,
});

const playbooksRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuidePlaybooksPage),
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
  ...guideLoading(GuidePlaybookPage),
  path: 'playbooks/$id',
  component: PlaybookRoute,
});

const situationsRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideSituationsPage),
  path: 'situations',
  component: GuideSituationsPage,
});

function SituationRoute() {
  const { slug } = situationRoute.useParams();
  return <GuideSituationPage slug={slug} />;
}

const situationRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideSituationPage),
  path: 'situations/$slug',
  component: SituationRoute,
});

const regimeIndexRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideRegimePage),
  path: 'regime',
  component: GuideRegimePage,
});

function IndicatorRoute() {
  const { key } = indicatorRoute.useParams();
  return <GuideIndicatorPage indicatorKey={key} />;
}

const indicatorRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideIndicatorPage),
  path: 'regime/indicators/$key',
  component: IndicatorRoute,
});

function EpisodeRoute() {
  const { key } = episodeRoute.useParams();
  return <GuideEpisodePage slug={key} />;
}

const episodeRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideEpisodePage),
  path: 'regime/episodes/$key',
  component: EpisodeRoute,
});

const startIndexRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideStartIndexPage),
  path: 'start',
  component: GuideStartIndexPage,
});

function StartRoute() {
  const { id } = startRoute.useParams();
  return <GuideStartPage id={id} />;
}

const startRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideStartPage),
  path: 'start/$id',
  component: StartRoute,
});

const glossaryRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideGlossaryPage),
  path: 'glossary',
  component: GuideGlossaryPage,
});

function TermRoute() {
  const { id } = termRoute.useParams();
  return <GuideTermPage id={id} />;
}

const termRoute = createRoute({
  getParentRoute: () => guideRoute,
  ...guideLoading(GuideTermPage),
  path: 'glossary/$id',
  component: TermRoute,
});

export const guideRoutes = guideRoute.addChildren([
  homeRoute,
  startIndexRoute,
  startRoute,
  fieldsRoute,
  fieldRoute,
  playbooksRoute,
  playbookRoute,
  situationsRoute,
  situationRoute,
  regimeIndexRoute,
  indicatorRoute,
  episodeRoute,
  glossaryRoute,
  termRoute,
]);
