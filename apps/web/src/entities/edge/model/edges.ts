/**
 * The edge model: the `EdgesPage` list rows and the `EdgeDetail` edge (ADR 0053, ED8) as the pages show
 * them. Each edge keeps what the server sent, verdict included: the verdict, its reason, every figure and sentence are
 * the read model's, so this only names the labels and tones of the served codes and their order.
 */
import type { StatusTone } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

export type EdgesResponse = gqlTypes.EdgesPageQuery;
/** One row of the list: the edge's own fields and the headline of its verdict (`summary`). */
export type EdgeRow = NonNullable<EdgesResponse['edgeList']>['items'][number];
/** One edge in full (the `EdgeDetail` read): the whole verdict, definition and runs. */
export type Edge = gqlTypes.EdgeDetailQuery['edges'][number];
/** One edge's document, as the builder reads it (no verdict, no runs). */
export type EdgeDocument = gqlTypes.EdgeDocumentQuery['edges'][number];
export type EdgeVerdict = Edge['verdict'];
export type VerdictCriterion = EdgeVerdict['criteria'][number];
export type EdgeProblem = gqlTypes.EdgeProblemsQuery['edgeProblems'][number];
export type VerdictYear = EdgeVerdict['years'][number];
export type VerdictColumn = EdgeVerdict['columns'][number];
export type EvidenceProgress = NonNullable<EdgeVerdict['evidence']>;

/** The verdicts, best first: the list's groups in this order. */
export const VERDICT_ORDER = [
  'works',
  'promising',
  'not_working',
  'not_enough_data',
  'waiting_on_data',
  'diagnostic_only',
] as const;

const VERDICT_LABELS: Record<string, string> = {
  works: 'Works',
  promising: 'Promising',
  not_working: 'Not working',
  not_enough_data: 'Not enough data',
  waiting_on_data: 'Waiting on data',
  diagnostic_only: 'Diagnostic only',
};

const VERDICT_TONES: Record<string, StatusTone> = {
  works: 'positive',
  promising: 'warning',
  not_working: 'negative',
  not_enough_data: 'info',
  waiting_on_data: 'neutral',
  diagnostic_only: 'neutral',
};

export const verdictLabel = (verdict: string): string => VERDICT_LABELS[verdict] ?? verdict;

export const verdictTone = (verdict: string): StatusTone => VERDICT_TONES[verdict] ?? 'neutral';

/** The statuses an edge has (ADR 0053 amendment 2026-10-10), in the order of its life. */
export const STATUSES = [
  'researching',
  'candidate',
  'evidenced',
  'live',
  'retired',
  'rejected',
  'blocked',
] as const;

const STATUS_LABELS: Record<string, string> = {
  researching: 'Researching',
  candidate: 'Candidate',
  evidenced: 'Evidenced',
  live: 'Live',
  retired: 'Retired',
  rejected: 'Rejected',
  blocked: 'Blocked',
};

/** An edge status as the list words it ("candidate" to "Candidate"). */
export const statusLabel = (status: string): string => STATUS_LABELS[status] ?? status;

const TONES: Record<string, StatusTone> = {
  evidenced: 'positive',
  live: 'positive',
  candidate: 'info',
  researching: 'neutral',
  blocked: 'warning',
  retired: 'neutral',
  rejected: 'negative',
};

export function statusTone(status: string): StatusTone {
  return TONES[status] ?? 'neutral';
}

const STATE_LABELS: Record<string, string> = {
  researching: 'Researching',
  following: 'Following',
  rejected: 'Rejected',
  retired: 'Retired',
  trial: 'Trial',
};

const STATE_TONES: Record<string, StatusTone> = {
  following: 'positive',
  trial: 'info',
  rejected: 'negative',
};

export const stateLabel = (state: string): string => STATE_LABELS[state] ?? state;

export const stateTone = (state: string): StatusTone => STATE_TONES[state] ?? 'neutral';

/** The permanent warnings the server puts on an edge, as chips (the Guide explains them). */
const LABEL_TEXTS: Record<string, string> = {
  followed_against_verdict: 'Followed against the verdict',
  oos_viewed_during_tuning: 'Out-of-sample seen while tuning',
  replaced_without_forward_test: 'Replaced without a forward test',
  split_moved_after_viewing: 'Split moved after viewing',
};

export const labelText = (label: string): string => LABEL_TEXTS[label] ?? label;

/** The side of the verdict's outcome, named when it is not the usual long side (`long`). */
const SIDE_LABELS: Record<string, string> = { short: 'Short', long_short: 'Long-short' };

export const sideLabel = (side: string): string | null => SIDE_LABELS[side] ?? null;

/** The state the list shows: the user's own, else the site's status for an edge not yet theirs. */
export const stateOrStatus = (edge: Pick<EdgeRow, 'state' | 'status'>): string =>
  edge.state === 'researching' ? statusLabel(edge.status) : stateLabel(edge.state);
