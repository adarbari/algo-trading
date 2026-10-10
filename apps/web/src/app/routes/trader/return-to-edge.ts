/**
 * The Screen Builder opened from an edge's builder (ADR 0053 amendment, ED8): the route search
 * `returnTo=<edge id>` (`NEW_EDGE` for an edge not saved yet) tells the Screen Builder it was
 * opened from there, so it offers "Save and return to edge", which goes back in history (the
 * edge's draft is kept meanwhile; the builder adds the screen made there).
 */

/** `returnTo` of an edge that has no id yet (it cannot be an edge id: `.` is not allowed in one). */
export const NEW_EDGE = '.new';
