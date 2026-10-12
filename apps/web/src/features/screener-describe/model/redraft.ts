/**
 * Why a retyped part did not come back, as the trader reads it. Each refusal is one kind with a
 * short title here and its explanation a Guide entry (ADR 0051): the model's own failures read as
 * a draft failure does (`failure.ts`), the daily limit on part redrafts is its own kind (no
 * Try again: asking again cannot work until the exchange day turns), and a screen that changed
 * while the model worked is one the browser noticed itself (the answer was built on the old
 * rows, so it is not applied). The server's text is never shown. Pure.
 */
import { ApiError } from '@/shared/api';

import { draftFailure, type DraftFailureKind } from './failure';
import type { TermRef } from './labels';

/** What the API's 429 for a user at their daily limit says (`LimitReached.code`). */
export const LIMIT_CODE = 'part_redraft_limit';

export type PartFailureKind = DraftFailureKind | 'limit' | 'stale';

export interface PartFailure {
  kind: PartFailureKind;
  /** The short message shown on the card. */
  title: string;
  /** The Guide term that explains it. */
  help: TermRef;
  /** Asking again can work. */
  retry: boolean;
}

const LIMIT: PartFailure = {
  kind: 'limit',
  title: 'Daily limit of part redrafts reached',
  help: { kind: 'term', id: 'describe_part_limit' },
  retry: false,
};

/** The answer was built on rows the trader has since changed: it is dropped, not merged over them. */
export const STALE: PartFailure = {
  kind: 'stale',
  title: 'Your screen changed while this redrafted',
  help: { kind: 'term', id: 'describe_part_stale' },
  retry: true,
};

export function partFailure(error: unknown): PartFailure {
  if (error instanceof ApiError && error.status === 429 && error.code === LIMIT_CODE) return LIMIT;
  return draftFailure(error);
}
