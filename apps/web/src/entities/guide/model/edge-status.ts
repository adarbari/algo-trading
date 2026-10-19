/**
 * How the Guide shows an edge's status and an idea's published verdict: the word and the tone of
 * its pill. The values are the server's (`GuideEdgeRow.status`, `GuideIdea.verdict`); the
 * meaning of each is a glossary term (`edge_status`, `idea_verdict`), never text here.
 */
import type { StatusTone } from '@algotrade/ui';

const STATUS_TONES: Readonly<Record<string, StatusTone>> = {
  evidenced: 'positive',
  live: 'positive',
  candidate: 'info',
  blocked: 'warning',
  rejected: 'negative',
};

const VERDICT_TONES: Readonly<Record<string, StatusTone>> = {
  strong: 'positive',
  promising: 'info',
  weak: 'warning',
  decayed: 'warning',
  dead: 'negative',
};

/** An edge status as a label ("candidate" to "Candidate"). */
export function edgeStatusText(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

const SIDE_TEXTS: Readonly<Record<string, string>> = {
  long: 'Long',
  short: 'Short',
  long_short: 'Long and short',
};

/** The side of an edge as a label (the words of the index's side filter). */
export function edgeSideText(side: string): string {
  return SIDE_TEXTS[side] ?? side;
}

/** The pill tone of an edge status. */
export function edgeStatusTone(status: string): StatusTone {
  return STATUS_TONES[status] ?? 'neutral';
}

/** The pill tone of an idea's published verdict (not graded: neutral). */
export function ideaVerdictTone(verdict: string): StatusTone {
  return VERDICT_TONES[verdict] ?? 'neutral';
}
