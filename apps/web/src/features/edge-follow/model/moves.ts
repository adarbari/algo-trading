/**
 * The moves a user may make about an edge from each state: the API's `TRANSITIONS` (it refuses
 * any other and decides the permanent warning labels itself), named as the buttons say them.
 */
import type { Edge } from '@/entities/edge';

export type Move = 'follow' | 'reject' | 'retire' | 'reopen' | 'reveal';

const FROM: Record<string, readonly Move[]> = {
  researching: ['follow', 'reject'],
  trial: ['follow', 'reject', 'reopen'],
  following: ['retire', 'reopen'],
  rejected: ['reopen'],
  retired: ['reopen'],
};

export const movesFrom = (state: string): readonly Move[] => FROM[state] ?? [];

/** The state a move leads to (`reveal` only shows the out-of-sample result). */
export const TARGET: Record<Move, string | undefined> = {
  reveal: undefined,
  follow: 'following',
  reject: 'rejected',
  retire: 'retired',
  reopen: 'researching',
};

export const MOVE_LABELS: Record<Move, string> = {
  follow: 'Follow',
  reject: 'Reject',
  retire: 'Retire',
  reopen: 'Back to researching',
  reveal: 'Show out-of-sample',
};

/** Showing the out-of-sample result is for a copy of the user's whose result is still withheld. */
export const canReveal = (edge: Edge): boolean => edge.mine && edge.oosHidden;

/** Rejecting needs a reason; retiring may give one. */
export const asksReason = (move: Move): boolean => move === 'reject' || move === 'retire';

/** The verdicts a follow warns about (the server decides the label; this only shows the reason). */
export const warnsFollow = (edge: Edge): boolean =>
  edge.verdict.verdict === 'not_working' || edge.verdict.verdict === 'not_enough_data';

const ID = /^[a-z0-9_-]{1,64}$/;

/** A new edge's id: 1-64 of a-z, 0-9, _ and - (the API's rule). */
export const isEdgeId = (id: string): boolean => ID.test(id);
