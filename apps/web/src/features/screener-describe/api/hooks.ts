/**
 * The draft-from-text POST (`POST /screeners/{id}/draft-from-text`, ADR 0041): the sentence and
 * the Builder's current document in, a draft document with what was dropped and the model's
 * notes out. Nothing is saved: the Builder loads the answer as an unsaved edit. The id of the
 * previous answer goes back with the next sentence so the descriptions of one screen stay one
 * feedback session (ADR 0066).
 */
import { useMutation } from '@tanstack/react-query';

import type { ScreenDocument } from '@/entities/screen';
import { api, unwrap, type components } from '@/shared/api';

export type ScreenDraft = components['schemas']['ScreenDraft'];

export function useDraftFromText(id: string) {
  return useMutation({
    mutationFn: ({
      text,
      document,
      draftSessionId,
    }: {
      text: string;
      document: ScreenDocument;
      draftSessionId?: string | null;
    }) =>
      unwrap(
        api.POST('/screeners/{screener_id}/draft-from-text', {
          params: { path: { screener_id: id } },
          body: { text, document, ...(draftSessionId ? { draft_session_id: draftSessionId } : {}) },
        }),
      ),
  });
}
