/**
 * The words and tones of the data-status popover: the dataset names and the status of each
 * (the server decides which applies; ADR 0056). Apart from `data-status.ts` so only the popover's
 * lazy chunk carries them, not the entry.
 */
import type { StatusTone } from '@algotrade/ui';

import type { DatasetName, DatasetState } from './data-status';

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
