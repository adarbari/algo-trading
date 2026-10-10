/**
 * The draft kept while the user is in the Screen Builder (opened from step 2) and back again:
 * one draft per edge, held in memory for this visit (a reload starts from the saved edge).
 * Cleared by a save or Cancel.
 */
import type { EdgeDraft } from './draft';

const held = new Map<string, EdgeDraft>();

/** Key of the not-yet-saved new edge. */
export const NEW_KEY = '(new)';

export const stash = (key: string, draft: EdgeDraft): void => {
  held.set(key, draft);
};

export const unstash = (key: string): EdgeDraft | undefined => held.get(key);

export const clearStash = (key: string): void => {
  held.delete(key);
};
