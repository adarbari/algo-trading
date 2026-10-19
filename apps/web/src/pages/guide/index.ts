/** Page: the Guide (home, Start here, glossary, field, playbook, situation, market regime and Edges pages). */
import { prefetchFeatureCatalogue } from '@/entities/feature';
import { prefetchGuideIndex } from '@/entities/guide';

/** Start the reads every Guide page shares before it mounts (the route's loader). */
export function prefetchGuideReads(client: Parameters<typeof prefetchGuideIndex>[0]): void {
  prefetchGuideIndex(client);
  prefetchFeatureCatalogue(client);
}

export {
  GuideEdgePage,
  GuideEdgesPage,
  GuideEpisodePage,
  GuideFieldPage,
  GuideFieldsPage,
  GuideGlossaryPage,
  GuideHomePage,
  GuideIndicatorPage,
  GuideMechanismPage,
  GuidePlaybookPage,
  GuidePlaybooksPage,
  GuideRegimePage,
  GuideSituationPage,
  GuideSituationsPage,
  GuideStartIndexPage,
  GuideStartPage,
  GuideTermPage,
  type GuideEdgePageProps,
  type GuideEdgesPageProps,
  type GuideFieldPageProps,
  type GuideFieldsPageProps,
  type GuidePlaybookPageProps,
} from './ui/GuidePages';
