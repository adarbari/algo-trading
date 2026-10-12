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

/** The badge text of a part's kind and the Guide term that explains it. */
const PART_KINDS: Record<string, { label: string; help: TermRef }> = {
  applied: { label: 'Applied', help: { kind: 'term', id: 'describe_applied' } },
  formula: { label: 'Formula to review', help: { kind: 'term', id: 'describe_proposed_formulas' } },
  needs_choice: {
    label: 'Needs your call',
    help: { kind: 'term', id: 'describe_needs_your_call' },
  },
  not_available: {
    label: 'Not available yet',
    help: { kind: 'term', id: 'describe_not_available_yet' },
  },
  not_understood: {
    label: 'Not understood',
    help: { kind: 'term', id: 'describe_part_not_understood' },
  },
};

export function partKindLabel(kind: string): { label: string; help: TermRef } {
  return PART_KINDS[kind] ?? (PART_KINDS['not_understood'] as { label: string; help: TermRef });
}

/** The fixed words of a part card (labels; each has its Guide term beside it). */
export const PART_TEXT = {
  reading: 'We read this as',
  checkReading: 'Check this reading',
  readingHelp: { kind: 'term', id: 'describe_part_reading' } as TermRef,
  keptTitle: 'Kept from your screen',
  keptMark: 'Not from the sentence',
  unplacedTitle: 'Not tied to your words',
  keptHelp: { kind: 'term', id: 'describe_part_kept' } as TermRef,
  edited: 'Edited',
  editedHelp: { kind: 'term', id: 'describe_part_edited' } as TermRef,
  redrafting: 'Redrafting this part',
  list: 'Parts of your sentence',
  rankedBy: 'Ranked by',
  rankHelp: { kind: 'term', id: 'describe_part_rank' } as TermRef,
  suggested: 'Suggested',
  suggestedHelp: { kind: 'term', id: 'describe_suggested' } as TermRef,
  add: 'Add',
  skip: 'Skip',
  added: 'Added',
  skipped: 'Skipped',
} as const;
