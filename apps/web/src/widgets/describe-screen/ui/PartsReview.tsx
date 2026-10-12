/**
 * The draft review of "Describe it" as one card per part of the sentence (docs/drafting/
 * describe-it-plan.md "Explained parts"): the trader's own words quoted, "We read this as ..." in
 * plain language, then what that part owns: its criteria (the Builder's rows, by id), the formula
 * to review, the readings of an ambiguous term (picking another swaps the row locally, no model
 * call), the feature that is not available yet (the trader's OWN history only) and the protective
 * checks suggested (added or skipped, never applied silently). Words nothing understood and
 * criteria kept from the screen are cards of their own. The server decides every part, kind and
 * reference; a card is marked edited when the trader changed its rows (ADR 0038). Zero applied
 * criteria is not an error: the Builder's document stays.
 */
import { Mono, PartCard, PartList, Stack, Text } from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import { GuideHelp, termHelp } from '@/features/guide-help';
import {
  PART_TEXT,
  appliedRows,
  partEdited,
  partKindLabel,
  partsOf,
  readingSwap,
  suggestionsOf,
  useMyFeatureRequests,
  type DraftPart,
  type DraftSuggestion,
  type MissingFeature,
  type ScreenDraft,
  type Unresolved,
} from '@/features/screener-describe';

import { MissingCard, NotCovered, missingKey } from './NotAvailable';
import { CriteriaRows, Readings, Suggested, type SuggestionState } from './PartRows';
import { FormulaCard } from './ProposedFormulas';
import type { DraftReviewProps } from './props';

/** The criteria the draft left out of a part, as the answer lists them. */
function leftOut(part: DraftPart, answer: ScreenDraft): ScreenDraft['dropped'] {
  return answer.dropped.filter((d) => part.dropped.includes(d.id));
}

/** The field the screen ranks by, when it has one. */
function tieBreakOf(document: Readonly<Record<string, unknown>>): string | null {
  const rank = document['rank'];
  const field =
    typeof rank === 'object' && rank !== null && 'tie_break' in rank ? rank.tie_break : null;
  return typeof field === 'string' && field !== '' ? field : null;
}

export function PartsReview({
  answer,
  document,
  formulaStates,
  notes,
  onRemoveNote,
  onReviewFormula,
  onSkipFormula,
  onPickReading,
  onAcceptSuggestion,
  renderFieldHelp,
}: DraftReviewProps) {
  const parts = partsOf(answer);
  const unresolved = answer.unresolved ?? [];
  const formulas = answer.formulas ?? [];
  const missing: readonly MissingFeature[] = answer.missing ?? [];
  const suggestions = suggestionsOf(answer);
  const [picked, setPicked] = useState<Readonly<Record<string, number>>>({});
  const [decided, setDecided] = useState<Readonly<Record<string, SuggestionState>>>({});
  // The history is a nicety: a failed read leaves the cards without it.
  const history = useMyFeatureRequests(missing.length > 0);
  const mine = history.data ?? [];

  const selectedOf = (term: Unresolved) => picked[term.term] ?? term.default_index;
  const pick = (term: Unresolved, to: number) => {
    const swap = readingSwap(document, term, selectedOf(term), to);
    if (!swap) return;
    setPicked((now) => ({ ...now, [term.term]: to }));
    onPickReading(swap, { event: 'choice_made', subject: term.term, picked: to });
  };
  const add = (suggestion: DraftSuggestion) => {
    onAcceptSuggestion(suggestion.criterion);
    setDecided((now) => ({ ...now, [suggestion.id]: 'added' }));
  };
  const skip = (id: string) => {
    setDecided((now) => ({ ...now, [id]: 'skipped' }));
  };
  const suggestedIn = (ids: readonly string[]) => suggestions.filter((s) => ids.includes(s.id));
  const owned = new Set(parts.flatMap((part) => part.suggestions));
  const unowned = suggestions.filter((s) => !owned.has(s.id));

  const original = answer.document['criteria'];
  const current = document['criteria'];
  const rowsNow = appliedRows(document);

  const rowsOf = (part: DraftPart): ReactNode => {
    const criteria = rowsNow.filter((row) => part.criteria.includes(row.id));
    const dropped = leftOut(part, answer);
    const own = formulas.filter((f) => part.formulas.includes(f.name));
    const gaps = missing.filter((item) => part.missing.includes(missingKey(item)));
    const offered = suggestedIn(part.suggestions);
    const rankField = part.rank ? tieBreakOf(document) : null;
    if (
      criteria.length + dropped.length + own.length + gaps.length + offered.length === 0 &&
      !rankField
    )
      return null;
    return (
      <Stack gap={3}>
        {(criteria.length > 0 || dropped.length > 0) && (
          <CriteriaRows rows={criteria} dropped={dropped} renderFieldHelp={renderFieldHelp} />
        )}
        {rankField && (
          <Stack direction="row" gap={1} align="center" wrap>
            <Text size="sm" tone="muted">
              {PART_TEXT.rankedBy}
            </Text>
            <Mono size="sm">{rankField}</Mono>
            {renderFieldHelp?.(rankField)}
            {termHelp(PART_TEXT.rankHelp.id)}
          </Stack>
        )}
        {own.map((formula) => (
          <FormulaCard
            key={formula.name}
            formula={formula}
            state={formulaStates[formula.name] ?? 'proposed'}
            onReview={onReviewFormula}
            onSkip={onSkipFormula}
          />
        ))}
        {gaps.map((item) => (
          <MissingCard
            key={missingKey(item)}
            item={item}
            mine={mine}
            renderFieldHelp={renderFieldHelp}
          />
        ))}
        <Suggested
          suggestions={offered}
          states={decided}
          onAdd={add}
          onSkip={skip}
          renderFieldHelp={renderFieldHelp}
        />
      </Stack>
    );
  };

  const pickersOf = (part: DraftPart): ReactNode => {
    const terms = unresolved.filter((term) => part.unresolved.includes(term.term));
    if (terms.length === 0) return null;
    return (
      <Stack gap={3}>
        {terms.map((term) => (
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
    );
  };

  const cardOf = (part: DraftPart) => {
    const kind = partKindLabel(part.kind);
    const edited = partEdited(part, original, current, answer.unresolved);
    const common = {
      kind: part.kind,
      kindLabel: kind.label,
      origin: part.origin === 'gap' ? 'words' : part.origin,
      keptLabel: PART_TEXT.keptMark,
      readingLabel: PART_TEXT.reading,
      reading: part.reading,
      readingSource: part.reading_source,
      checkReadingLabel: PART_TEXT.checkReading,
      rows: rowsOf(part),
      redraftingLabel: PART_TEXT.redrafting,
      edited,
      editedLabel: PART_TEXT.edited,
    } as const;
    const helps = (
      <Stack direction="row" gap={1} align="center">
        <GuideHelp entry={kind.help} />
        {part.reading_source !== 'model' && part.words !== '' && (
          <GuideHelp entry={PART_TEXT.readingHelp} />
        )}
        {edited && <GuideHelp entry={PART_TEXT.editedHelp} />}
      </Stack>
    );
    return part.origin === 'words' || part.origin === 'gap' ? (
      <PartCard
        key={part.id}
        {...common}
        words={part.words}
        actions={pickersOf(part)}
        info={helps}
      />
    ) : (
      <PartCard
        key={part.id}
        {...common}
        title={part.origin === 'kept' ? PART_TEXT.keptTitle : PART_TEXT.unplacedTitle}
        info={helps}
        actions={
          <Stack gap={2}>
            {pickersOf(part)}
            {termHelp(PART_TEXT.keptHelp.id)}
          </Stack>
        }
      />
    );
  };

  const leftover = [
    ...(answer.formulas_dropped ?? []).map((d) => `Left out ${d.name}: ${d.reason}`),
    ...answer.notes,
  ];

  return (
    <Stack gap={3}>
      <PartList aria-label={PART_TEXT.list}>{parts.map(cardOf)}</PartList>
      {unowned.length > 0 && (
        <Suggested
          suggestions={unowned}
          states={decided}
          onAdd={add}
          onSkip={skip}
          renderFieldHelp={renderFieldHelp}
        />
      )}
      {leftover.map((line) => (
        <Text key={line} size="sm" tone="muted">
          {line}
        </Text>
      ))}
      <NotCovered notes={notes} onRemoveNote={onRemoveNote} />
    </Stack>
  );
}
