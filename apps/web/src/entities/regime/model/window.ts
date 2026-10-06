/**
 * The window a regime history chart shows (RG7): a preset counted back from the regime's
 * session, or one episode's window (a year before its peak to six months after its recovery).
 * Dates move by calendar arithmetic on the session the server gave, never the browser's today.
 */
import { addMonths } from '@/shared/lib/date';

import type { HistoryWindow } from './history';
import type { RegimeEpisode } from './regime';

/** The oldest day the stored history can reach (the NBER list and the index series start here). */
export const HISTORY_START = '1971-01-01';

export type RangePreset = 'all' | '20y' | '10y' | '5y' | '2y';

export const RANGE_PRESETS: readonly { value: RangePreset; label: string; years: number | null }[] =
  [
    { value: 'all', label: 'All', years: null },
    { value: '20y', label: '20y', years: 20 },
    { value: '10y', label: '10y', years: 10 },
    { value: '5y', label: '5y', years: 5 },
    { value: '2y', label: '2y', years: 2 },
  ];

/** The preset's window ending at `session` (All: from `HISTORY_START`). */
export function presetWindow(preset: RangePreset, session: string): HistoryWindow {
  const years = RANGE_PRESETS.find((p) => p.value === preset)?.years ?? null;
  return { start: years === null ? HISTORY_START : addMonths(session, -12 * years), end: session };
}

/** An episode's window: a year before its peak to six months after its recovery (else the session). */
export function episodeWindow(episode: RegimeEpisode, session: string): HistoryWindow {
  const after = episode.recovered === null ? session : addMonths(episode.recovered, 6);
  return { start: addMonths(episode.peak, -12), end: after > session ? session : after };
}
