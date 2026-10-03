/** The review lists' open-ended rows as symbol + detail (a note, else the name). */
import type { ReviewItem, ReviewList } from './types';

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

export function reviewItems(list: ReviewList): ReviewItem[] {
  return list.items.map((row) => ({
    symbol: text(row['symbol']) || text(row['instrument_id']),
    detail: text(row['note']) || text(row['name']),
  }));
}
