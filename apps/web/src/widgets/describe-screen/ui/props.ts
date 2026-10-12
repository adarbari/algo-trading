/**
 * The props of the draft review: the answer, the Builder's working document and what the trader
 * decides on the answer's options (a reading, a formula, a suggestion). Shared by the parts
 * review and the grouped one it falls back to.
 */
import type { ReactNode } from 'react';

import type { Criterion, ScreenDocument } from '@/entities/screen';
import type { DraftChoice, FormulaState } from '@/features/screener-builder';
import type { DraftFormula, DraftPart, ScreenDraft } from '@/features/screener-describe';

export interface DraftReviewProps {
  answer: ScreenDraft;
  /** The Builder's working document (the swap finds the row of a reading in it). */
  document: ScreenDocument;
  formulaStates: Readonly<Record<string, FormulaState>>;
  /** The screen's "not covered" notes (kept with the screen) and removing one. */
  notes: readonly string[];
  onRemoveNote: (note: string) => void;
  onReviewFormula: (formula: DraftFormula) => void;
  onSkipFormula: (name: string) => void;
  /** A reading was picked: the criterion that replaces the row, and the choice to record. */
  onPickReading: (criterion: Criterion, choice: DraftChoice) => void;
  /** A suggestion was accepted: its criterion joins the screen as a new row (soft or score). */
  onAcceptSuggestion: (criterion: Readonly<Record<string, unknown>>) => void;
  /** The help for a field the draft names (null for a field the Guide does not know). */
  renderFieldHelp?: ((field: string) => ReactNode) | undefined;
  /**
   * The server redrafted one part: `next` is the whole merged draft to show and load (the
   * Builder's document included), `prior` the one it replaces, `replaced` the part. Without it no
   * part offers a retype (the answer is shown, not edited).
   */
  onRedrafted?: ((next: ScreenDraft, prior: ScreenDraft, replaced: DraftPart) => void) | undefined;
}
