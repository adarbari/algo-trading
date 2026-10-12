/**
 * The words and Guide references of the review panel's states: how hard a missing feature is to
 * add (the draft's `feasibility`) and where the trader's own request for it stands (the backlog's
 * `status`). Each value has a short label (the badge) and the Guide term that explains it
 * (ADR 0051; the references are written out so the Guide-coverage test resolves each one).
 * A value the app does not know reads as the unclear one. Pure.
 */
import type { StatusTone } from '@algotrade/ui';

/** A reference to a glossary term (the shape the Guide's help button takes). */
export interface TermRef {
  kind: 'term';
  id: string;
}

export interface BadgeLabel {
  label: string;
  tone: StatusTone;
  help: TermRef;
}

const FEASIBILITY: Record<string, BadgeLabel> = {
  ROLLUP_FROM_STORED: {
    label: 'Buildable from stored data',
    tone: 'info',
    help: { kind: 'term', id: 'describe_feasibility_rollup' },
  },
  NEEDS_SOURCE: {
    label: 'Needs a new source',
    tone: 'warning',
    help: { kind: 'term', id: 'describe_feasibility_source' },
  },
  UNCLEAR: {
    label: 'Unclear',
    tone: 'neutral',
    help: { kind: 'term', id: 'describe_feasibility_unclear' },
  },
};

const STATUS: Record<string, BadgeLabel> = {
  OPEN: { label: 'Open', tone: 'neutral', help: { kind: 'term', id: 'describe_status_open' } },
  PROMOTED: {
    label: 'Promoted',
    tone: 'positive',
    help: { kind: 'term', id: 'describe_status_promoted' },
  },
  WONT_DO: {
    label: "Won't do",
    tone: 'neutral',
    help: { kind: 'term', id: 'describe_status_wont_do' },
  },
};

export function feasibilityLabel(feasibility: string): BadgeLabel {
  return FEASIBILITY[feasibility] ?? (FEASIBILITY['UNCLEAR'] as BadgeLabel);
}

/** The label of a request status; null for one the backlog does not define. */
export function statusLabel(status: string): BadgeLabel | null {
  return STATUS[status] ?? null;
}
