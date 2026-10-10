/**
 * The session notice (ADR 0062): the pages show the last complete session; `newer` is the later
 * one whose nightly workflow is still running or failing (its public kind only, never a step).
 * Plain data for the notice widget; the words and the term it opens are the widget's and the
 * Guide's.
 */
export interface SessionNotice {
  /** The session every page is showing. */
  served: string;
  newer: {
    date: string;
    state: 'IN_PROGRESS' | 'FAILED_RETRYING';
    kind: string | null;
  };
}
