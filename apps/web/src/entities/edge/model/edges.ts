/**
 * The edge model: the `EdgesPage` response (ADR 0053, ED8) as the pages show it. Each edge keeps
 * what the server sent, verdict included: the verdict, its reason, every figure and sentence are
 * the read model's, so this only names the labels and tones of the served codes and their order.
 */
import type { StatusTone } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

export type EdgesResponse = gqlTypes.EdgesPageQuery;
export type Edge = EdgesResponse['edges'][number];
export type EdgeVerdict = Edge['verdict'];
export type VerdictCriterion = EdgeVerdict['criteria'][number];
export type EdgeProblem = EdgesResponse['edgeProblems'][number];
export type EdgeCompare = NonNullable<Edge['compare']>;
export type CompareRow = EdgeCompare['rows'][number];
export type VerdictYear = EdgeVerdict['years'][number];

/** The verdicts, best first: the list's groups in this order. */
export const VERDICT_ORDER = [
  'works',
  'promising',
  'not_working',
  'not_enough_data',
  'waiting_on_data',
] as const;

const VERDICT_LABELS: Record<string, string> = {
  works: 'Works',
  promising: 'Promising',
  not_working: 'Not working',
  not_enough_data: 'Not enough data',
  waiting_on_data: 'Waiting on data',
};

const VERDICT_TONES: Record<string, StatusTone> = {
  works: 'positive',
  promising: 'warning',
  not_working: 'negative',
  not_enough_data: 'info',
  waiting_on_data: 'neutral',
};

export const verdictLabel = (verdict: string): string => VERDICT_LABELS[verdict] ?? verdict;

export const verdictTone = (verdict: string): StatusTone => VERDICT_TONES[verdict] ?? 'neutral';

/** An edge status as the list words it ("candidate" to "Candidate"). */
export function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

const TONES: Record<string, StatusTone> = {
  evidenced: 'positive',
  live: 'positive',
  candidate: 'info',
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

/** The list's views (a link keeps one): everything, the user's own edges, followed, rejected. */
export const EDGE_VIEWS = [
  { value: 'all', label: 'All' },
  { value: 'mine', label: 'Mine' },
  { value: 'following', label: 'Following' },
  { value: 'rejected', label: 'Rejected' },
] as const;

export type EdgeView = (typeof EDGE_VIEWS)[number]['value'];

/** Whether an edge belongs to a view (rejected: by the user, or the site's own verdict). */
export function inView(edge: Edge, view: EdgeView): boolean {
  if (view === 'mine') return edge.mine;
  if (view === 'following') return edge.state === 'following';
  if (view === 'rejected') return edge.state === 'rejected' || edge.status === 'rejected';
  return true;
}

/** The state the list shows: the user's own, else the site's status for an edge not yet theirs. */
export const stateOrStatus = (edge: Edge): string =>
  edge.state === 'researching' ? statusLabel(edge.status) : stateLabel(edge.state);
