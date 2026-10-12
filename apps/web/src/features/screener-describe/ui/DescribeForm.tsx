/**
 * "Describe it": a sentence ("optionable stocks over $5 with IV rank above 50%") sent for a
 * draft. The answer's criteria are handed to the Builder as unsaved rows (an answer with none
 * leaves the Builder's document alone) and what the model understood is shown by the owner's
 * review panel (`renderReview`: the widget composes it, features never import each other). A
 * draft takes 5 to 20 s, so the wait is visible and can be cancelled (the answer is then ignored);
 * a failure is a trader-facing message with Try again, never the API's raw text.
 */
import { Banner, Button, Field, Input, Skeleton, Stack, Text } from '@algotrade/ui';
import { useEffect, useRef, useState, type ReactNode } from 'react';

import type { ScreenDocument } from '@/entities/screen';

import { useDraftFromText, type ScreenDraft } from '../api/hooks';
import { draftFailure, wasCancelled } from '../model/failure';
import { hasCriteria } from '../model/review';

export interface DescribeFormProps {
  screenerId: string;
  /** The Builder's working document: its criteria are kept unless the sentence changes them. */
  document: ScreenDocument;
  /** The draft the model proposed: load it into the Builder as an unsaved edit. */
  onDraft: (document: Readonly<Record<string, unknown>>) => void;
  /**
   * The feedback session of this screen (ADR 0066): the id of the last answer, sent with the
   * next sentence; the owner (the Builder) keeps it across saves (the same id goes with
   * each save) and clears it on finalise, on discard and when another screen opens.
   */
  draftSessionId?: string | null;
  /** The answer's session id, to keep for the next sentence and the save. */
  onSession?: (draftSessionId: string | null) => void;
  /** An answer arrived (its options replace the last answer's): reset what was decided on them. */
  onAnswer?: (answer: ScreenDraft) => void;
  /** The help button of a Guide term (the failure message's explanation); features never import each other. */
  renderTermHelp?: (term: string) => ReactNode;
  /** The review of an answer: what was understood, what the draft proposes, what is missing. */
  renderReview?: (review: { answer: ScreenDraft; text: string; serial: number }) => ReactNode;
}

const HINT =
  'Plain English, e.g. "optionable stocks over $5 with IV rank above 50% and $50M traded a day". The rows are a draft you review.';

interface Answered {
  answer: ScreenDraft;
  text: string;
  /** Distinct per answer: the review starts afresh for a new one. */
  serial: number;
}

export function DescribeForm({
  screenerId,
  document,
  onDraft,
  draftSessionId = null,
  onSession,
  onAnswer,
  renderTermHelp,
  renderReview,
}: DescribeFormProps) {
  const [text, setText] = useState('');
  const [result, setResult] = useState<Answered | null>(null);
  const answers = useRef(0);
  const draft = useDraftFromText(screenerId);
  const flight = useRef<AbortController | null>(null);
  const waiting = draft.isPending;
  const canSubmit = text.trim() !== '' && !waiting;

  const submit = () => {
    if (!canSubmit) return;
    const sent = text.trim();
    const controller = new AbortController();
    flight.current = controller;
    draft.mutate(
      { text: sent, document, draftSessionId, signal: controller.signal },
      {
        onSuccess: (answer) => {
          if (controller.signal.aborted) return; // cancelled: the answer is ignored
          answers.current += 1;
          setResult({ answer, text: sent, serial: answers.current });
          onSession?.(answer.draft_session_id ?? null);
          onAnswer?.(answer);
          if (hasCriteria(answer.document)) onDraft(answer.document);
        },
      },
    );
  };
  // The session ended (finalised, discarded, another screen): the answer and its review go with it,
  // and a request still in flight is ignored (its answer would start a session on a finished screen).
  const hadSession = useRef(draftSessionId !== null);
  const reset = draft.reset;
  useEffect(() => {
    if (hadSession.current && draftSessionId === null) {
      flight.current?.abort();
      reset();
      setResult(null);
    }
    hadSession.current = draftSessionId !== null;
  }, [draftSessionId, reset]);
  const cancel = () => {
    flight.current?.abort();
    draft.reset();
  };

  const failure =
    draft.isError && !wasCancelled(draft.error) ? draftFailure(draft.error) : undefined;
  return (
    <Stack gap={3}>
      <Field label="Describe the screen" hint={HINT}>
        <Input
          value={text}
          onValueChange={setText}
          onKeyDown={(event) => {
            if (event.key === 'Enter') submit();
          }}
          placeholder="Which instruments, which thresholds, how to rank"
          autoComplete="off"
          end={
            <Button
              variant="primary"
              size="sm"
              onClick={submit}
              disabled={!canSubmit}
              loading={waiting}
            >
              Draft it
            </Button>
          }
        />
      </Field>
      {waiting && (
        <Stack gap={2}>
          <Skeleton lines={2} label="Drafting your screen" />
          <Stack direction="row" gap={2} align="center" wrap>
            <Text size="sm" tone="muted">
              Drafting, up to 20 seconds
            </Text>
            <Button variant="ghost" size="sm" onClick={cancel}>
              Cancel
            </Button>
          </Stack>
        </Stack>
      )}
      {failure && (
        <Banner
          tone="negative"
          title={failure.title}
          actions={
            <Stack direction="row" gap={2} align="center">
              {failure.retry && (
                <Button variant="secondary" size="sm" onClick={submit} disabled={!canSubmit}>
                  Try again
                </Button>
              )}
              {renderTermHelp?.(failure.help.id)}
            </Stack>
          }
        />
      )}
      {!waiting && result && renderReview?.(result)}
    </Stack>
  );
}
