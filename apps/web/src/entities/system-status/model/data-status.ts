/**
 * The session's data status for the pill (ADR 0056: the server's words and figures; the browser
 * derives none). The state, the datasets with their share and the screener counts come from
 * `Session.dataStatus`; this file only names them: the label maps (state, dataset, dataset
 * status) and the tone of each state, and shapes the response for the widget.
 */
import type { StatusTone } from '@algotrade/ui';

import type { ServedUnavailable } from '@/entities/availability';

export type DataState = 'COMPLETE' | 'PARTIAL' | 'NEXT_PROCESSING' | 'NEXT_FAILED_SHOWING_PREVIOUS';
export type DatasetName = 'PRICES' | 'OPTIONS_CHAINS' | 'FUNDAMENTALS';
export type DatasetState = 'COMPLETE' | 'PARTIAL' | 'MISSING' | 'UNKNOWN';

/** One dataset row of the popover. */
export interface DatasetView {
  name: DatasetName;
  status: DatasetState;
  /** Share of the expected names present, 0 to 1 (the server's; null: no record). */
  share: number | null;
  /** The gaps as served: an admin's carry the cause chain (the server sends it to admins only). */
  gaps: ReadonlyArray<Pick<ServedUnavailable, 'cause'>>;
}

export interface DataStatusView {
  /** The session the pages show. */
  date: string;
  /** The newer session processing or failed (null: none). */
  newerDate: string | null;
  state: DataState;
  /** When the session completed (null: not yet). */
  knowledgeTs: string | null;
  datasets: DatasetView[];
  affectedScreeners: number;
  totalScreeners: number;
}

export const DATASET_LABEL: Record<DatasetName, string> = {
  PRICES: 'Prices',
  OPTIONS_CHAINS: 'Options chains',
  FUNDAMENTALS: 'Fundamentals',
};

export const DATASET_STATE_LABEL: Record<DatasetState, string> = {
  COMPLETE: 'Complete',
  PARTIAL: 'Partial',
  MISSING: 'Missing',
  UNKNOWN: 'Unknown',
};

export const DATASET_STATE_TONE: Record<DatasetState, StatusTone> = {
  COMPLETE: 'positive',
  PARTIAL: 'warning',
  MISSING: 'negative',
  UNKNOWN: 'neutral',
};

export const DATA_STATE_TONE: Record<DataState, StatusTone> = {
  COMPLETE: 'positive',
  PARTIAL: 'warning',
  NEXT_PROCESSING: 'info',
  NEXT_FAILED_SHOWING_PREVIOUS: 'negative',
};

/** What the response carries of a session (a structural slice of the generated type). */
interface SessionData {
  date: string;
  newer?: { date: string } | null;
  dataStatus: {
    state: DataState;
    knowledgeTs?: string | null;
    datasets: Array<{
      name: DatasetName;
      status: DatasetState;
      share?: number | null;
      unavailable: Array<Pick<ServedUnavailable, 'cause'>>;
    }>;
    affectedScreeners: number;
    totalScreeners: number;
  };
}

export function dataStatusOf({ date, newer, dataStatus }: SessionData): DataStatusView {
  return {
    date,
    newerDate: newer?.date ?? null,
    state: dataStatus.state,
    knowledgeTs: dataStatus.knowledgeTs ?? null,
    datasets: dataStatus.datasets.map((d) => ({
      name: d.name,
      status: d.status,
      share: d.share ?? null,
      gaps: d.unavailable,
    })),
    affectedScreeners: dataStatus.affectedScreeners,
    totalScreeners: dataStatus.totalScreeners,
  };
}
