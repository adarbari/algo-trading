/** A run record as the app reads it: the served JSON (`itemsByStatus`, `stats`) as records. */
import type { RunDetail, ServedRunDetail } from './types';

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function toRunDetail(run: ServedRunDetail): RunDetail {
  const counts = Object.entries(record(run.itemsByStatus)).filter(
    (entry): entry is [string, number] => typeof entry[1] === 'number',
  );
  return { ...run, itemsByStatus: Object.fromEntries(counts), stats: record(run.stats) };
}
