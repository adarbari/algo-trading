/** Page: the Guide (home, Start here, glossary, field, playbook, situation and market regime pages). */
import { prefetchFeatureCatalogue } from '@/entities/feature';
import { prefetchGuideIndex } from '@/entities/guide';

/** Start the reads every Guide page shares before it mounts (the route's loader). */
export function prefetchGuideReads(client: Parameters<typeof prefetchGuideIndex>[0]): void {
  prefetchGuideIndex(client);
  prefetchFeatureCatalogue(client);
}

export {
  GuideEpisodePage,
  GuideFieldPage,
  GuideFieldsPage,
  GuideGlossaryPage,
  GuideHomePage,
  GuideIndicatorPage,
  GuidePlaybookPage,
  GuidePlaybooksPage,
  GuideRegimePage,
  GuideSituationPage,
  GuideSituationsPage,
  GuideStartIndexPage,
  GuideStartPage,
  GuideTermPage,
  type GuideFieldPageProps,
  type GuideFieldsPageProps,
  type GuidePlaybookPageProps,
} from './ui/GuidePages';
