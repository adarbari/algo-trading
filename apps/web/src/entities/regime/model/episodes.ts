/**
 * The reference market episodes a page names in plain words: the key the `episode_behaviour@v1`
 * features carry (`dd_<key>`, `recovery_sessions_<key>`) and the name a trader reads.
 *
 * TODO: the API does not serve the episodes config (`config/site/regime/episodes.toml`) yet, so
 * the plain names live here, newest first; read them from the API when the read model exposes
 * them, and drop this map.
 */

export interface Episode {
  /** The `episodes.toml` key and the feature-name suffix. */
  key: string;
  /** "Tariff shock, spring 2025". */
  name: string;
}

export const EPISODES: readonly Episode[] = [
  { key: 'tariffs_2025', name: 'Tariff shock, spring 2025' },
  { key: 'hikes_2022', name: 'Rate-hike bear market, 2022' },
  { key: 'covid_2020', name: 'Covid crash, early 2020' },
];

/** The plain name of an episode key (an unmapped key reads as itself, spaced). */
export function episodeName(key: string): string {
  return EPISODES.find((episode) => episode.key === key)?.name ?? key.replace(/_/g, ' ');
}
