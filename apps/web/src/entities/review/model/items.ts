/** The review lists' open-ended rows as symbol + detail (a note, else the name). */
import type { ReviewItem, ReviewList } from './types';

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

function record(value: unknown): Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

export function reviewItems(list: ReviewList | null | undefined): ReviewItem[] {
  return (list?.items ?? []).map((item) => {
    const row = record(item);
    return {
      symbol: text(row['symbol']) || text(row['instrument_id']),
      detail: text(row['note']) || text(row['name']),
    };
  });
}
