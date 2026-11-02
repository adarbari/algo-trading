/** Page: Trader > Ideas (the ticker-level ideas table with its views and filters). */
import { prefetchFilterSet } from '@/entities/filter';
import { prefetchSetupIdeas, type IdeaTab } from '@/entities/idea';
import { prefetchRegime } from '@/entities/regime';

export { IdeasPage, type IdeasPageProps } from './ui/IdeasPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchIdeasReads(
  client: Parameters<typeof prefetchSetupIdeas>[0],
  tab: IdeaTab = 'stocks',
): void {
  prefetchRegime(client);
  prefetchSetupIdeas(client, tab);
  prefetchFilterSet(client, 'ideas');
}
