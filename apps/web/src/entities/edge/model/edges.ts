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
