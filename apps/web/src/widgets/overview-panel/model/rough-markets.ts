/**
 * "In rough markets": how the focused instrument behaved against the market and in the
 * market's reference episodes, from the stored `episode_behaviour@v1` features (read by name,
 * ADR 0038): beta to SPY, then the drawdown in each episode with its plain name (from the
 * API's episodes: `Query.regime.episodes`) and, when the close has regained the pre-episode
 * high, the sessions it took. Values and their UNKNOWN
 * reasons read as every other fact does (`factItem`); a name with no value for an episode
 * (listed later, not enough bars) leaves the line out, and the group is empty when none has one.
 */
import type { KeyValueItem } from '@algotrade/ui';

import { episodeName, type RegimeEpisode } from '@/entities/regime';
import { feature, type SiteFeature } from '@/shared/api';

import { factItem, type FactGroup, type Values } from './overview';

const BETA = feature('rollup.episode_behaviour@v1.beta_252d');

/**
 * The drawdown and recovery features of each episode the nightly stores (the names are checked
 * literals: a new episode is a new column and version, not a config line), newest first.
 */
const EPISODE_FEATURES: Readonly<Record<string, { drawdown: SiteFeature; recovery: SiteFeature }>> =
  {
    tariffs_2025: {
      drawdown: feature('rollup.episode_behaviour@v1.dd_tariffs_2025'),
      recovery: feature('rollup.episode_behaviour@v1.recovery_sessions_tariffs_2025'),
    },
    hikes_2022: {
      drawdown: feature('rollup.episode_behaviour@v1.dd_hikes_2022'),
      recovery: feature('rollup.episode_behaviour@v1.recovery_sessions_hikes_2022'),
    },
    covid_2020: {
      drawdown: feature('rollup.episode_behaviour@v1.dd_covid_2020'),
      recovery: feature('rollup.episode_behaviour@v1.recovery_sessions_covid_2020'),
    },
  };

/** Every feature the line asks for (added to the Overview's one request). */
export const ROUGH_MARKET_FEATURES: readonly SiteFeature[] = [
  BETA,
  ...Object.values(EPISODE_FEATURES).flatMap((names) => [names.drawdown, names.recovery]),
];

const sessions = (n: unknown): string | null =>
  typeof n === 'number' && Number.isFinite(n)
    ? `Back at its pre-episode high ${n} session${n === 1 ? '' : 's'} after the low`
    : null;

/** `episodes`: the episodes the API knows for the session (names); a key it lacks reads spaced. */
export function roughMarketsGroup(values: Values, episodes: readonly RegimeEpisode[]): FactGroup {
  const items: KeyValueItem[] = [];
  const beta = factItem(values, { id: 'beta', label: 'Beta to SPY (1 year)', name: BETA });
  if (beta) items.push(beta);
  for (const [key, names] of Object.entries(EPISODE_FEATURES)) {
    const drawdown = factItem(values, {
      id: key,
      label: episodeName(episodes, key),
      name: names.drawdown,
      signed: true,
    });
    if (!drawdown) continue;
    const recovered = sessions(values.get(names.recovery)?.value);
    items.push(recovered && drawdown.format ? { ...drawdown, hint: recovered } : drawdown);
  }
  return { id: 'rough-markets', title: 'In rough markets', items };
}
