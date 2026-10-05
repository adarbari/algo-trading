/** The review entity's types: the owner's curation lists (FIGI conflicts, leveraged ETFs). */
import type { gqlTypes } from '@/shared/api';

export type ReviewList = NonNullable<gqlTypes.FigiReviewQuery['figiReview']>;

/** One item to review: its symbol and the reason it needs a look. */
export interface ReviewItem {
  symbol: string;
  detail: string;
}
