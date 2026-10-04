/**
 * Explore's URL search params for comparing the chosen ideas: the compare set (`sel`, at most
 * six: one chart colour each, as in Explore) and the ticker its detail tabs open on.
 */
export const MAX_COMPARE_IDEAS = 6;

export interface IdeaCompareSearch {
  sel: string;
  focus: string;
}

/** The search for `symbols` (pick order), or null when there is nothing to compare. */
export function compareSearch(symbols: readonly string[]): IdeaCompareSearch | null {
  const set = symbols.slice(0, MAX_COMPARE_IDEAS);
  const [first] = set;
  return first === undefined ? null : { sel: set.join(','), focus: first };
}
