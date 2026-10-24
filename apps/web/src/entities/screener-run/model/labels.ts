/**
 * How the Screener runs tab words the server's keys: the status tone and a stored timestamp.
 * Labels only: what a status means is a Guide entry.
 */
import type { StatusTone } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

/** A run record's status as the API's enum has it (generated: a new server status is a type error here). */
export type RunStatus = gqlTypes.RunStatus;

/** The words the page shows for each status (each has its Guide entry); keyed by the server's enum. */
const STATUS_TEXT: Record<RunStatus, string> = {
  QUEUED: 'queued',
  RUNNING: 'running',
  COMPLETE: 'complete',
  PARTIAL: 'partial',
  WAITING: 'waiting',
  FAILED: 'failed',
};

const TONES: Record<RunStatus, StatusTone> = {
  COMPLETE: 'positive',
  RUNNING: 'info',
  QUEUED: 'info',
  WAITING: 'info',
  PARTIAL: 'warning',
  FAILED: 'negative',
};

/** Every status the server can record, from the generated enum's own keys. */
export const RUN_STATUSES = Object.keys(STATUS_TEXT) as RunStatus[];

export const statusText = (status: RunStatus): string => STATUS_TEXT[status];

export const statusTone = (status: RunStatus): StatusTone => TONES[status];

/** A stored timestamp as UTC to the minute. */
export const stamp = (ts: string) => `${ts.replace('T', ' ').slice(0, 16)} UTC`;
