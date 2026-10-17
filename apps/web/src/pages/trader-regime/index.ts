/** Page: Trader > Regime (the market as weather, its warning signs, the reading list). */
import { prefetchRegimeEpisodes, prefetchRegimeSignals } from '@/entities/regime';

export { RegimePage } from './ui/RegimePage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them.
 * The regime itself is read with every layout (the route guard). */
export function prefetchRegimeReads(client: Parameters<typeof prefetchRegimeEpisodes>[0]): void {
  prefetchRegimeEpisodes(client);
  prefetchRegimeSignals(client);
}
