/**
 * How the Harness runs tab words the server's keys: the status tone, a stored timestamp, a run's
 * range and split, and a variant at a horizon. Labels only: what a term means is a Guide entry.
 */
import type { StatusTone } from '@algotrade/ui';

import type { HarnessRow } from './types';

const TONES: Record<string, StatusTone> = {
  complete: 'positive',
  running: 'info',
  partial: 'warning',
  failed: 'negative',
};

export const statusTone = (status: string): StatusTone => TONES[status] ?? 'neutral';

/** A stored timestamp as UTC to the minute. */
export const stamp = (ts: string) => `${ts.replace('T', ' ').slice(0, 16)} UTC`;

/** The sessions a run covered ("2012-01-03 to 2026-10-02"; an unrecorded start as an ellipsis). */
export const rangeText = (from: string | null | undefined, to: string) => `${from ?? '…'} to ${to}`;

/** A row's variant, for the rows table: the edge variant (not `main`), the screener or baseline. */
export function rowLabel(row: HarnessRow): string {
  const prefix = row.edgeVariant === 'main' ? '' : `${row.edgeVariant} · `;
  return `${prefix}${row.variant} (${row.role})`;
}

/** A stable row key within one run. */
export const rowKey = (row: HarnessRow): string =>
  [row.edgeVariant, row.role, row.variant, row.horizonSessions, row.sliceKind, row.sliceValue].join(
    '/',
  );
