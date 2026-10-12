/**
 * How the feature-requests page words the server's keys: a status badge tone, the status and
 * feasibility filters, and the Guide term each served value opens. Labels only: what a value
 * means is a Guide entry.
 */
import type { StatusTone } from '@algotrade/ui';

/** The served statuses, in the order the filter lists them. */
export const STATUSES = ['OPEN', 'PROMOTED', 'WONT_DO', 'UNMAPPED'] as const;
export type RequestStatus = (typeof STATUSES)[number];

export const STATUS_LABEL: Record<RequestStatus, string> = {
  OPEN: 'Open',
  PROMOTED: 'Promoted',
  WONT_DO: "Won't do",
  UNMAPPED: 'Unmapped',
};

const TONES: Record<RequestStatus, StatusTone> = {
  OPEN: 'info',
  PROMOTED: 'positive',
  WONT_DO: 'neutral',
  UNMAPPED: 'warning',
};

export const isRequestStatus = (value: unknown): value is RequestStatus =>
  typeof value === 'string' && (STATUSES as readonly string[]).includes(value);

export const statusTone = (status: string): StatusTone =>
  isRequestStatus(status) ? TONES[status] : 'neutral';

export const statusLabel = (status: string): string =>
  isRequestStatus(status) ? STATUS_LABEL[status] : status;

/** The glossary terms: feasibility, status, score and the unmapped flag. */
export const TERM_OF_FEASIBILITY = 'feature_request_feasibility';

export const START_PAGE = 'read_feature_requests';
export const TERM_OF_STATUS = 'feature_request_status';
export const TERM_OF_SCORE = 'feature_request_score';
export const TERM_OF_UNMAPPED = 'feature_request_unmapped';
