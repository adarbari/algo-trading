/** The review entity's types: the owner's curation lists (FIGI conflicts, leveraged ETFs). */
import type { components } from '@/shared/api';

export type ReviewList = components['schemas']['ReviewList'];

/** One item to review: its symbol and the reason it needs a look. */
export interface ReviewItem {
  symbol: string;
  detail: string;
}
