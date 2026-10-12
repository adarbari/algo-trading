/**
 * One part card that can be retyped (docs/drafting/describe-it-plan.md "Explained parts", PR C2):
 * the card the review built, with a "Retype this part" button; the words become an input with
 * Redraft / Cancel, and Redraft asks the server to redraft that part alone (one scoped model call,
 * counted against the daily limit). Only this card shows the wait (`redrafting`); the others stay
 * usable but cannot start a retype of their own while one is in flight. A part the trader edited by
 * hand asks first ("This replaces your edits to this part."). On success the browser swaps in the
 * merged draft the server returned (`onRedrafted`); it derives nothing (ADR 0038). A failure is an
 * inline message with Try again, the daily limit its own message with no retry, and an answer that
 * arrives after the trader changed the screen is dropped (it was built on the old rows) with the
 * same Try again. A wait cannot be cancelled (the spec makes only the whole draft cancellable): the
 * card is inert until the answer or the failure comes. Cancel leaves the input with the words as
 * they were; focus returns to the Retype button.
 */
import { Button, Dialog, PartCard, Stack, type PartCardProps } from '@algotrade/ui';
import { useEffect, useRef, useState } from 'react';

import type { ScreenDocument } from '@/entities/screen';
import { GuideHelp, termHelp } from '@/features/guide-help';
import {
  PART_TEXT,
  STALE,
  partFailure,
  useRedraftPart,
  type DraftPart,
  type PartFailure,
  type ScreenDraft,
} from '@/features/screener-describe';

/** The longest words a part may have (the server's cap, `MAX_WORDS`). */
const MAX_WORDS = 200;

type Mode = 'closed' | 'typing' | 'confirming';

export interface RetypeCardProps {
  /** The card the review built for this part (its words, reading, rows, pickers and helps). */
  card: PartCardProps;
  part: DraftPart;
  /** The draft the card belongs to (sent back whole) and the Builder's working document. */
  answer: ScreenDraft;
  document: ScreenDocument;
  /** The trader changed this part's rows: replacing them asks first. */
  edited: boolean;
  /** The part being redrafted now (any card), or null: only one retype at a time. `on` false clears it only if it is this part's. */
  redrafting: string | null;
  onRedrafting: (partId: string, on: boolean) => void;
  /** The trader's daily limit of part redrafts was reached (known from any card). */
  limited: boolean;
  onLimited: (retryAfterS: number | undefined) => void;
  /** The merged draft came back: the owner swaps it in. */
  onRedrafted: (next: ScreenDraft, replaced: DraftPart) => void;
}

const squash = (text: string) => text.split(/\s+/).filter(Boolean).join(' ');

export function RetypeCard({
  card,
  part,
  answer,
  document,
  edited,
  redrafting,
  onRedrafting,
  limited,
  onLimited,
  onRedrafted,
}: RetypeCardProps) {
  const [mode, setMode] = useState<Mode>('closed');
  const [value, setValue] = useState(part.words);
  const [failure, setFailure] = useState<PartFailure | null>(null);
  const redraft = useRedraftPart(answer.screener_id);
  const button = useRef<HTMLButtonElement>(null);
  const focusBack = useRef(false);
  const flight = useRef<AbortController | null>(null);
  const inFlight = useRef(false);
  const settle = useRef(onRedrafting);
  // The document the trader has now, read when the answer arrives (not the one it was asked on).
  const latest = useRef(document);
  useEffect(() => {
    latest.current = document;
  });
  useEffect(() => {
    settle.current = onRedrafting;
  });
  // Leaving the page mid-wait: the call is abandoned (still counted), the one-at-a-time flag freed.
  useEffect(
    () => () => {
      flight.current?.abort();
      if (inFlight.current) settle.current(part.id, false);
    },
    [part.id],
  );
  useEffect(() => {
    if (mode === 'closed' && focusBack.current) {
      focusBack.current = false;
      button.current?.focus();
    }
  }, [mode]);

  const words = squash(value);
  const pending = redraft.isPending;
  // Another card's retype is in flight: this one waits (one retype at a time).
  const busy = redrafting !== null && redrafting !== part.id;
  const canApply = words !== '' && words !== part.words && !pending && !limited && !busy;
  // The limit cleared (its time elapsed): the message about it goes, Redraft works again.
  const shown = failure?.kind === 'limit' && !limited ? null : failure;

  const open = () => {
    setValue(part.words);
    setFailure(null);
    setMode('typing');
  };
  const leave = () => {
    setFailure(null);
    focusBack.current = true;
    setMode('closed');
  };
  const send = () => {
    if (!canApply) return;
    const sent = document;
    const controller = new AbortController();
    flight.current = controller;
    setFailure(null);
    setMode('typing');
    inFlight.current = true;
    onRedrafting(part.id, true);
    redraft.mutate(
      { answer, document: sent, partId: part.id, newWords: words, signal: controller.signal },
      {
        onSuccess: (done) => {
          if (controller.signal.aborted) return;
          if (latest.current !== sent) {
            setFailure(STALE);
            return;
          }
          setMode('closed');
          onRedrafted(done.draft, part);
        },
        onError: (error) => {
          if (controller.signal.aborted) return;
          const failed = partFailure(error);
          if (failed.kind === 'limit') onLimited(failed.retryAfterS);
          setFailure(failed);
        },
        onSettled: () => {
          inFlight.current = false;
          onRedrafting(part.id, false);
        },
      },
    );
  };
  const apply = () => {
    if (!canApply) return;
    if (edited) setMode('confirming');
    else send();
  };

  const retyping = mode !== 'closed';
  const state = pending ? 'redrafting' : shown ? 'error' : 'idle';
  const retypeButton = (
    <Stack direction="row" gap={1} align="center">
      <Button size="sm" variant="ghost" ref={button} disabled={busy || limited} onClick={open}>
        {PART_TEXT.retype}
      </Button>
      {termHelp(limited ? PART_TEXT.limitHelp.id : PART_TEXT.retypeHelp.id)}
    </Stack>
  );

  return (
    <>
      <PartCard
        {...card}
        state={state}
        actions={
          <Stack gap={3}>
            {card.actions}
            {!retyping && retypeButton}
          </Stack>
        }
        info={
          <Stack direction="row" gap={1} align="center">
            {card.info}
            {shown && <GuideHelp entry={shown.help} />}
          </Stack>
        }
        {...(shown ? { errorMessage: shown.title } : {})}
        {...(shown?.retry ? { retryLabel: PART_TEXT.tryAgain, onRetry: apply } : {})}
        {...(retyping
          ? {
              retype: {
                value,
                onValueChange: setValue,
                onApply: apply,
                onCancel: leave,
                inputLabel: PART_TEXT.retype,
                applyLabel: PART_TEXT.redraft,
                cancelLabel: PART_TEXT.cancel,
                maxLength: MAX_WORDS,
                applyDisabled: !canApply,
              },
            }
          : {})}
      />
      <Dialog
        open={mode === 'confirming'}
        onOpenChange={(next) => {
          if (!next) setMode('typing');
        }}
        size="sm"
        title={PART_TEXT.confirmTitle}
        description={PART_TEXT.confirmEdits}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setMode('typing');
              }}
            >
              {PART_TEXT.cancel}
            </Button>
            <Button variant="primary" onClick={send}>
              {PART_TEXT.redraft}
            </Button>
          </>
        }
      />
    </>
  );
}
