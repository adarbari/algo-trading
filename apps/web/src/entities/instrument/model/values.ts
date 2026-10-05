/**
 * An instrument's catalogue features as the read model serves them for the session (values
 * with UNKNOWN reasons) and per session over a window (the history behind a sparkline), asked
 * in chunks of names the API accepts in one request.
 */
import type { ServedValue } from '@/entities/feature';

/** Every value asked for, by catalogue name, and the session they are for. */
export interface FeatureValues {
  /** The session's ISO day (null: not answered yet, or nothing stored). */
  session: string | null;
  values: ReadonlyMap<string, ServedValue>;
  isPending: boolean;
  isError: boolean;
  refetch: () => Promise<unknown>;
}

/** One answered chunk of a feature history: `values` of each point follow `names`. */
export interface SeriesChunk {
  names: readonly string[];
  points: readonly { session: string; values: readonly unknown[] }[];
}

export interface FeatureHistory {
  series: readonly SeriesChunk[];
  isPending: boolean;
}

/** `names` in runs of at most `size`, in order. */
export function chunks(names: readonly string[], size: number): string[][] {
  const out: string[][] = [];
  for (let i = 0; i < names.length; i += size) out.push(names.slice(i, i + size));
  return out;
}

/** One feature's values over the sessions, oldest first (non-numbers are gaps); null when no
 * answered chunk has it. */
export function historyOf(history: FeatureHistory, name: string): (number | null)[] | null {
  for (const chunk of history.series) {
    const at = chunk.names.indexOf(name);
    if (at < 0) continue;
    return chunk.points.map((p) => {
      const value = p.values[at];
      return typeof value === 'number' && Number.isFinite(value) ? value : null;
    });
  }
  return null;
}
