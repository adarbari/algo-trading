/** The evaluation line's state labels, tones and Guide terms (the server decides the state). */
import type { StatusTone } from '@algotrade/ui';

/** The evaluation line's state (the server decides it): its badge and the Guide entry for it. */
const PROVENANCE_LABELS: Record<string, string> = {
  CURRENT: 'Current',
  STALE: 'Stale',
  RE_EVALUATING: 'Re-evaluating',
};

const PROVENANCE_TONES: Record<string, StatusTone> = {
  CURRENT: 'positive',
  STALE: 'warning',
  RE_EVALUATING: 'info',
};

const PROVENANCE_TERMS: Record<string, string> = {
  CURRENT: 'provenance_current',
  STALE: 'provenance_stale',
  RE_EVALUATING: 'provenance_re_evaluating',
};

export const provenanceLabel = (state: string): string => PROVENANCE_LABELS[state] ?? state;

export const provenanceTone = (state: string): StatusTone => PROVENANCE_TONES[state] ?? 'neutral';

/** The Guide term that explains the state (the generic evaluation line for an unknown one). */
export const provenanceTerm = (state: string): string =>
  PROVENANCE_TERMS[state] ?? 'edge_provenance';
