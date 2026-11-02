/**
 * The draft review of "Describe it" as one card per part of the sentence (docs/drafting/
 * describe-it-plan.md "Explained parts"): the trader's own words quoted, "We read this as ..." in
 * plain language, then what that part owns: its criteria (the Builder's rows, by id), the formula
 * to review, the readings of an ambiguous term (picking another swaps the row locally, no model
 * call) and the feature that is not available yet (the trader's OWN history only). The model only
 * translates the sentence: nothing here adds a rule the trader did not write (ADR 0083 decision
 * 4). Words nothing understood and
 * criteria kept from the screen are cards of their own. The server decides every part, kind and
 * reference; a card is marked edited when the trader changed its rows (ADR 0038). Zero applied
 * criteria is not an error: the Builder's document stays.
 */
import { Mono, PartCard, PartJoin, PartList, Stack, Text, type PartCardProps } from '@algotrade/ui';
import { useEffect, useState, type ReactNode } from 'react';

import { GuideHelp, termHelp } from '@/features/guide-help';
import {
  JOIN_TEXT,
  PART_TEXT,
  appliedRows,
  baselineAfter,
  joinToken,
  partEdited,
  partKindLabel,
  partsOf,
  readingSwap,
  useMyFeatureRequests,
  type DraftPart,
  type MissingFeature,
  type ScreenDraft,
  type Unresolved,
} from '@/features/screener-describe';

import { MissingCard, NotCovered, missingKey } from './NotAvailable';
import { CriteriaRows, Readings } from './PartRows';
import { FormulaCard } from './ProposedFormulas';
import { RetypeCard } from './RetypePart';
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

/** The longest a timer may run (setTimeout's own limit is 2^31 - 1 ms). */
const MAX_TIMER_MS = 2 ** 31 - 1;

export function PartsReview({
  answer,
  document,
  formulaStates,
  notes,
  onRemoveNote,
  onReviewFormula,
  onSkipFormula,
  onPickReading,
  onRedrafted,
  renderFieldHelp,
}: DraftReviewProps) {
  const parts = partsOf(answer);
  const unresolved = answer.unresolved ?? [];
  const formulas = answer.formulas ?? [];
  const missing: readonly MissingFeature[] = answer.missing ?? [];
  const [picked, setPicked] = useState<Readonly<Record<string, number>>>({});
  // What the answer's own rows were, to tell the trader's edits from them. A retype replaces the
  // answer, so the rows of the parts it did not touch stay as first shown (their edits still show).
  const [original, setOriginal] = useState<unknown>(answer.document['criteria']);
  // The part being redrafted (one at a time) and whether the daily limit was reached.
  const [redrafting, setRedrafting] = useState<string | null>(null);
  // The daily limit was reached: `seconds` until it clears (null: not limited; undefined seconds:
  // the server did not say, so it stays until the page reloads). One timer lifts it for every card.
  const [limit, setLimit] = useState<{ seconds: number | undefined } | null>(null);
  const limited = limit !== null;
  useEffect(() => {
    if (limit?.seconds === undefined) return;
    const timer = setTimeout(
      () => {
        setLimit(null);
      },
      Math.min(Math.max(limit.seconds, 0) * 1000, MAX_TIMER_MS),
    );
    return () => {
      clearTimeout(timer);
    };
  }, [limit]);
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

  const current = document['criteria'];
  const rowsNow = appliedRows(document);

  const redrafted = (next: ScreenDraft, replaced: DraftPart) => {
    setOriginal((before: unknown) => baselineAfter(before, next, replaced));
    // What was decided on the redrafted part's own options is void: its readings are new.
    setPicked((now) =>
      Object.fromEntries(
        Object.entries(now).filter(([term]) => !replaced.unresolved.includes(term)),
      ),
    );
    onRedrafted?.(next, answer, replaced);
  };

  const rowsOf = (part: DraftPart): ReactNode => {
    const criteria = rowsNow.filter((row) => part.criteria.includes(row.id));
    const dropped = leftOut(part, answer);
    const own = formulas.filter((f) => part.formulas.includes(f.name));
    const gaps = missing.filter((item) => part.missing.includes(missingKey(item)));
    const rankField = part.rank ? tieBreakOf(document) : null;
    if (criteria.length + dropped.length + own.length + gaps.length === 0 && !rankField) return null;
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
    if (part.origin === 'words' || part.origin === 'gap') {
      const card: PartCardProps = {
        ...common,
        words: part.words,
        actions: pickersOf(part),
        info: helps,
      };
      // The sentence is needed to retype one part of it (an answer without it cannot).
      return onRedrafted && answer.sentence ? (
        <RetypeCard
          key={part.id}
          card={card}
          part={part}
          answer={answer}
          document={document}
          edited={edited}
          redrafting={redrafting}
          onRedrafting={(id, on) => {
            // Cleared only by the card that set it: a late settle must not free another's turn.
            setRedrafting((now) => (on ? id : now === id ? null : now));
          }}
          limited={limited}
          onLimited={(seconds) => {
            setLimit({ seconds });
          }}
          onRedrafted={redrafted}
        />
      ) : (
        <PartCard key={part.id} {...card} />
      );
    }
    return (
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

  // A connector sits directly before the card it joins (PartList reads it unwrapped).
  const withJoin = (part: DraftPart) => {
    const token = joinToken(part);
    return token
      ? [
          <PartJoin
            key={`join-${part.id}`}
            {...token}
            joinedByLabel={JOIN_TEXT.joinedBy}
            readAsLabel={JOIN_TEXT.readAs}
            info={<GuideHelp entry={JOIN_TEXT.help} />}
          />,
          cardOf(part),
        ]
      : [cardOf(part)];
  };

  const leftover = [
    ...(answer.formulas_dropped ?? []).map((d) => `Left out ${d.name}: ${d.reason}`),
    ...answer.notes,
  ];

  return (
    <Stack gap={3}>
      <PartList aria-label={PART_TEXT.list}>{parts.flatMap(withJoin)}</PartList>
      {leftover.map((line) => (
        <Text key={line} size="sm" tone="muted">
          {line}
        </Text>
      ))}
      <NotCovered notes={notes} onRemoveNote={onRemoveNote} />
    </Stack>
  );
}
