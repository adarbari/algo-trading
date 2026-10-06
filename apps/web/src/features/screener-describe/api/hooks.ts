/**
 * The draft-from-text POST (`POST /screeners/{id}/draft-from-text`, ADR 0040): the sentence and
 * the Builder's current document in, a draft document with what was dropped and the model's
 * notes out. Nothing is saved: the Builder loads the answer as an unsaved edit.
 */
import { useMutation } from '@tanstack/react-query';

import type { ScreenDocument } from '@/entities/screen';
import { api, unwrap, type components } from '@/shared/api';

export type ScreenDraft = components['schemas']['ScreenDraft'];

export function useDraftFromText(id: string) {
  return useMutation({
    mutationFn: ({ text, document }: { text: string; document: ScreenDocument }) =>
      unwrap(
        api.POST('/screeners/{screener_id}/draft-from-text', {
          params: { path: { screener_id: id } },
          body: { text, document },
        }),
      ),
  });
}
