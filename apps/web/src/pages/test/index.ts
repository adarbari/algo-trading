/**
 * Page group: the Test flow (`/test`): Start (the four ways in and the list of screeners), Guided
 * (templates), Expert and Describe it (a new draft, then the rules), the Result of a screener and
 * the setup builder. The steps at the top of each page are `TestSteps`.
 */
import { lazyPage } from '@/shared/lib/lazy';
import { decodeFilters } from '@/features/filter-bar';
import { prefetchTrackRecords } from '@/entities/edge';
import {
  prefetchMyScreens,
  prefetchScreenerList,
  prefetchScreenerRuns,
  prefetchScreeners,
} from '@/entities/screen';
export { TEST_PATHS } from './ui/paths';
export { TestGuidedPage, type TestGuidedPageProps } from './ui/TestGuidedPage';
export { TestNewPage, type TestNewPageProps } from './ui/TestNewPage';

// Start (the list and the filter bar), Expert, the Result and the setup builder are heavy: each its
// own chunk, so a route loads only its own. The routes preload the one they open (`.preload`), so
// it renders unsuspended.
export const TestStartPage = lazyPage(() => import('./ui/TestStartPage'), 'TestStartPage');
export const TestExpertPage = lazyPage(() => import('./ui/TestExpertPage'), 'TestExpertPage');
export const TestResultPage = lazyPage(() => import('./ui/TestResultPage'), 'TestResultPage');
export const TestSetupPage = lazyPage(() => import('./ui/TestSetupPage'), 'TestSetupPage');

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchTestStartReads(
  client: Parameters<typeof prefetchScreeners>[0],
  f?: string,
  q = '',
): Promise<void> {
  prefetchScreenerList(client, decodeFilters(f), q);
  prefetchScreeners(client);
  prefetchMyScreens(client);
  prefetchScreenerRuns(client);
  prefetchTrackRecords(client);
  return TestStartPage.preload();
}

export type { TestStartPageProps, TestWay } from './ui/TestStartPage';
export type { TestExpertPageProps } from './ui/TestExpertPage';
export type { TestResultPageProps } from './ui/TestResultPage';
export type { TestSetupPageProps } from './ui/TestSetupPage';
