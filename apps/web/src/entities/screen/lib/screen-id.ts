/**
 * The screen id rule, apart from the spec model so the copy dialog and the new-screener form
 * do not load the Builder's document code with it.
 */

/** A screen id the API accepts: 1-64 of [a-z0-9_-]. */
export const isScreenId = (id: string): boolean => /^[a-z0-9_-]{1,64}$/.test(id);
