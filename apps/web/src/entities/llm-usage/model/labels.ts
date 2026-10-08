/**
 * The names the usage page gives the server's keys (window, breakdown, cost basis, outcome), the
 * tone each reads in, the value formats and the identity of a stored call. Labels only: what a
 * term means is a Guide entry (`TERM_OF_BASIS`), never text here.
 */
import type { ValueFormat } from '@algotrade/ui';

import type { LlmUsage, UsageCall } from './types';

export const USD: ValueFormat = { kind: 'currency', digits: 4 };
export const TOKENS: ValueFormat = { kind: 'number' };
export const PERCENT: ValueFormat = { kind: 'percent', digits: 1 };

export const WINDOW_LABEL: Record<string, string> = {
  today: 'Today',
  '7d': 'Last 7 days',
  '30d': 'Last 30 days',
  month: 'Month to date',
};

export const BREAKDOWN_LABEL: Record<string, string> = {
  model: 'Model',
  use_case: 'Use case',
  user: 'User',
  cost_basis: 'Cost basis',
  outcome: 'Outcome',
};

export const BASIS_LABEL: Record<string, string> = {
  price: 'Priced',
  reported: 'Reported (notional)',
  bound: 'Bound',
  free: 'Free',
  unknown: 'Unknown',
};

/** The Guide glossary term that explains a cost basis. */
export const TERM_OF_BASIS = 'llm_cost_basis';

export type BasisTone = 'accent' | 'info' | 'warning' | 'neutral';

export function basisTone(basis: string): BasisTone {
  if (basis === 'price') return 'accent';
  if (basis === 'reported') return 'info';
  if (basis === 'bound') return 'warning';
  return 'neutral';
}

export function outcomeTone(outcome: string): 'positive' | 'warning' | 'negative' | 'neutral' {
  if (outcome === 'ok') return 'positive';
  if (outcome === 'fell_back') return 'warning';
  if (outcome === 'failed') return 'negative';
  return 'neutral';
}

/** The label of a breakdown key (a cost basis reads as its name; a null key as the dash). */
export function sliceLabel(by: string, key: string | null | undefined): string {
  if (key == null) return '—';
  return by === 'cost_basis' ? (BASIS_LABEL[key] ?? key) : key;
}

/** A stored timestamp as the log's UTC time. */
export const stamp = (ts: string) => `${ts.replace('T', ' ').slice(0, 19)} UTC`;

/** A stored call's identity: the key the recorder merges on (`ts`, `provider`, `use_case`). */
export function callId(call: UsageCall): string {
  return `${call.ts}~${call.provider}~${call.useCase}`;
}

export function findCall(usage: LlmUsage | null | undefined, id: string | null): UsageCall | null {
  if (!usage || !id) return null;
  return usage.recent.find((c) => callId(c) === id) ?? null;
}
