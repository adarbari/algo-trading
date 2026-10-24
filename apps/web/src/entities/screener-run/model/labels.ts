/**
 * How the Screener runs tab words the server's keys: the status tone and a stored timestamp.
 * Labels only: what a status means is a Guide entry.
 */
import type { StatusTone } from '@algotrade/ui';

const TONES: Record<string, StatusTone> = {
  complete: 'positive',
  running: 'info',
  queued: 'info',
  waiting: 'info',
  partial: 'warning',
  failed: 'negative',
};

export const statusTone = (status: string): StatusTone => TONES[status] ?? 'neutral';

/** A stored timestamp as UTC to the minute. */
export const stamp = (ts: string) => `${ts.replace('T', ' ').slice(0, 16)} UTC`;
