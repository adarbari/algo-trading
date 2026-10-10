/**
 * The draft kept while the user is in the Screen Builder (opened from step 2) and back again:
 * one per edge, held in memory for this visit (a reload starts from the saved edge), with the
 * screens that existed when it left so the ones made meanwhile can be added. Cleared by a save
 * or Cancel.
 */
import type { EdgeDraft } from './draft';

export interface Stashed {
  draft: EdgeDraft;
  /** The ids of the screens there were when the user left. */
  known: string[];
}

const held = new Map<string, Stashed>();

/** Key of the not-yet-saved new edge. */
export const NEW_KEY = '(new)';

export const stash = (key: string, draft: EdgeDraft, known: string[]): void => {
  held.set(key, { draft, known });
};

export const unstash = (key: string): Stashed | undefined => held.get(key);

export const clearStash = (key: string): void => {
  held.delete(key);
};
