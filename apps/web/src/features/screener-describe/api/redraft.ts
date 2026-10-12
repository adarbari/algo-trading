/**
 * The retype-one-part POST (`POST /screeners/{id}/draft-part`, ADR 0041 amended 2026-10-12): the
 * draft the browser holds (its sentence, parts and the items they point at, with the Builder's
 * current document in place of the answer's own), the part and its new words in; the whole merged
 * draft and the id of the part it replaced out. Nothing is saved and nothing is derived here: the
 * server re-checks every part and id, and the caller swaps its draft for the answer. One scoped
 * model call (3 to 10 s), counted against the user's daily limit (a 429 whose code is
 * `part_redraft_limit`), so the call can be cancelled (`signal`).
 */
import { useMutation } from '@tanstack/react-query';

import type { ScreenDocument } from '@/entities/screen';
import { api, unwrap, type components } from '@/shared/api';

import type { ScreenDraft } from './hooks';

export type DraftPartResult = components['schemas']['DraftPartResult'];

export interface RedraftRequest {
  /** The draft the trader is looking at, as served (or as the last redraft returned it). */
  answer: ScreenDraft;
  /** The Builder's working document, the trader's edits included. */
  document: ScreenDocument;
  partId: string;
  newWords: string;
  /** Aborting it cancels the request. */
  signal?: AbortSignal;
}

export function useRedraftPart(screenerId: string) {
  return useMutation({
    mutationFn: ({ answer, document, partId, newWords, signal }: RedraftRequest) =>
      unwrap(
        api.POST('/screeners/{screener_id}/draft-part', {
          params: { path: { screener_id: screenerId } },
          body: {
            sentence: answer.sentence ?? '',
            parts: answer.parts ?? [],
            document,
            part_id: partId,
            new_words: newWords,
            dropped: answer.dropped,
            formulas: answer.formulas ?? [],
            formulas_dropped: answer.formulas_dropped ?? [],
            missing: answer.missing ?? [],
            notes: answer.notes,
            suggestions: answer.suggestions ?? [],
            suggestions_dropped: answer.suggestions_dropped ?? [],
            unresolved: answer.unresolved ?? [],
            ...(answer.draft_session_id ? { draft_session_id: answer.draft_session_id } : {}),
          },
          ...(signal ? { signal } : {}),
        }),
      ),
  });
}
