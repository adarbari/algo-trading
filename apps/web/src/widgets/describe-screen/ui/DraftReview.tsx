/**
 * The draft review of "Describe it": what the model understood from the sentence, in four groups
 * (ADR 0066, docs/drafting/describe-it-plan.md "Web"). The sentence is echoed with each span the
 * server named tagged (needs your call, not available yet: text and underline, never colour
 * alone). Then Applied (the criteria loaded into the Builder), Proposed formulas (to review),
 * Needs your call (the readings of an ambiguous term; picking one swaps that criterion locally,
 * with no second model call) and Not available yet (requested, not applied). It is one lazy chunk
 * (the Builder loads it when an answer arrives). Zero applied criteria is not an error: the
 * Builder's document stays and the groups that have content show.
 */
import {
  Mono,
  Panel,
  SegmentedControl,
  Stack,
  StatusBadge,
  TaggedSentence,
  Text,
} from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import type { Criterion, ScreenDocument } from '@/entities/screen';
import { termHelp } from '@/features/guide-help';
import type { DraftChoice, FormulaState } from '@/features/screener-builder';
import {
  appliedRows,
  readingSwap,
  tagSentence,
  type DraftFormula,
  type MissingFeature,
  type ScreenDraft,
  type Unresolved,
} from '@/features/screener-describe';

import { NotAvailable } from './NotAvailable';
import { ProposedFormulas } from './ProposedFormulas';

export interface DraftReviewProps {
  answer: ScreenDraft;
  /** The sentence the answer is for. */
  text: string;
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
  /** The help for a field the draft names (null for a field the Guide does not know). */
  renderFieldHelp?: (field: string) => ReactNode;
}

function Readings({
  term,
  selected,
  swappable,
  onPick,
}: {
  term: Unresolved;
  selected: number;
  swappable: boolean;
  onPick: (to: number) => void;
}) {
  return (
    <Stack gap={1}>
      <Mono size="sm">{term.term}</Mono>
      <SegmentedControl
        aria-label={`Reading of ${term.term}`}
        options={term.alternatives.map((alternative, i) => ({
          value: String(i),
          label: alternative.text,
        }))}
        value={String(selected)}
        disabled={!swappable}
        onValueChange={(value) => {
          onPick(Number(value));
        }}
      />
    </Stack>
  );
}

export default function DraftReview({
  answer,
  text,
  document,
  formulaStates,
  notes,
  onRemoveNote,
  onReviewFormula,
  onSkipFormula,
  onPickReading,
  renderFieldHelp,
}: DraftReviewProps) {
  const unresolved = answer.unresolved ?? [];
  const formulas = answer.formulas ?? [];
  const missing: readonly MissingFeature[] = answer.missing ?? [];
  const [picked, setPicked] = useState<Readonly<Record<string, number>>>({});
  const selectedOf = (term: Unresolved) => picked[term.term] ?? term.default_index;

  const loaded = new Set(Object.keys(answer.document['criteria'] ?? {}));
  const rows = appliedRows(document).filter((row) => loaded.has(row.id));
  const leftOut = answer.dropped.length + (answer.formulas_dropped?.length ?? 0);
  const nothing =
    rows.length + leftOut + unresolved.length + formulas.length + missing.length === 0;
  const segments = tagSentence(text, [
    ...unresolved.map((term) => ({ span: term.span, kind: 'ask' as const })),
    ...missing.map((item) => ({ span: item.span, kind: 'gap' as const })),
  ]);

  const pick = (term: Unresolved, to: number) => {
    const swap = readingSwap(document, term, selectedOf(term), to);
    if (!swap) return;
    setPicked((now) => ({ ...now, [term.term]: to }));
    onPickReading(swap, { event: 'choice_made', subject: term.term, picked: to });
  };

  return (
    <Stack gap={3}>
      {segments.some((s) => s.kind !== 'plain') && (
        <TaggedSentence segments={segments} aria-label="What was understood" />
      )}
      <Panel
        title="Applied"
        headingLevel={3}
        actions={
          <Stack direction="row" gap={2} align="center">
            <StatusBadge tone={rows.length > 0 ? 'positive' : 'neutral'}>
              {rows.length > 0 ? 'Loaded in the Builder' : 'Nothing applied'}
            </StatusBadge>
            {termHelp('describe_applied')}
          </Stack>
        }
      >
        <Stack gap={1}>
          {rows.map(({ id, field }) => (
            <Stack key={id} direction="row" gap={1} align="center" wrap>
              <Text size="sm" tone="muted">{`${id}:`}</Text>
              <Mono size="sm">{field}</Mono>
              {renderFieldHelp?.(field)}
            </Stack>
          ))}
          {answer.dropped.map((d) => (
            <Stack key={d.id} direction="row" gap={1} align="center" wrap>
              <Text size="sm">{`Left out ${d.id} (`}</Text>
              <Mono size="sm">{d.field}</Mono>
              {renderFieldHelp?.(d.field)}
              <Text size="sm">{`): ${d.reason}`}</Text>
            </Stack>
          ))}
          {(answer.formulas_dropped ?? []).map((d) => (
            <Text key={d.name} size="sm">{`Left out ${d.name}: ${d.reason}`}</Text>
          ))}
          {answer.notes.map((note) => (
            <Text key={note} size="sm" tone="muted">
              {note}
            </Text>
          ))}
          {nothing && <Text size="sm">Nothing in that sentence could be applied</Text>}
        </Stack>
      </Panel>
      {formulas.length > 0 && (
        <ProposedFormulas
          formulas={formulas}
          states={formulaStates}
          onReview={onReviewFormula}
          onSkip={onSkipFormula}
        />
      )}
      {unresolved.length > 0 && (
        <Panel
          title="Needs your call"
          description="The model's reading is loaded; pick another to swap it"
          headingLevel={3}
          actions={
            <Stack direction="row" gap={2} align="center">
              <StatusBadge tone="warning">Default loaded</StatusBadge>
              {termHelp('describe_needs_your_call')}
            </Stack>
          }
        >
          <Stack gap={3}>
            {unresolved.map((term) => (
              <Readings
                key={term.term}
                term={term}
                selected={selectedOf(term)}
                swappable={readingSwap(document, term, selectedOf(term), selectedOf(term)) !== null}
                onPick={(to) => {
                  pick(term, to);
                }}
              />
            ))}
          </Stack>
        </Panel>
      )}
      {missing.length > 0 && (
        <NotAvailable
          missing={missing}
          notes={notes}
          onRemoveNote={onRemoveNote}
          renderFieldHelp={renderFieldHelp}
        />
      )}
    </Stack>
  );
}
