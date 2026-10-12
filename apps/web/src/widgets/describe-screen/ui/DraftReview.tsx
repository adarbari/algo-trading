/**
 * The draft review of "Describe it" (ADR 0066, docs/drafting/describe-it-plan.md "Explained
 * parts"): one card per part of the sentence when the answer carries parts (`PartsReview`), the
 * four grouped panels when it does not (`GroupedReview`, an answer recorded before parts existed).
 * It is one lazy chunk (the Builder loads it when an answer arrives), so both views ship in it.
 */
import { partsOf } from '@/features/screener-describe';

import { GroupedReview } from './GroupedReview';
import { PartsReview } from './PartsReview';
import type { DraftReviewProps } from './props';

export type { DraftReviewProps } from './props';

export default function DraftReview(props: DraftReviewProps) {
  return partsOf(props.answer).length > 0 ? (
    <PartsReview {...props} />
  ) : (
    <GroupedReview {...props} />
  );
}
