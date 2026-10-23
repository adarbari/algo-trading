/**
 * What a Screeners row shows of a run, chosen from the served values: the new / dropped counts
 * since the previous run. Pure; nothing is recounted.
 */
export interface Changes {
  added: number;
  dropped: number;
}

/** The served `new` / `dropped` counts; null when the run has no previous run to compare with. */
export function changesOf(changes: readonly { change: string; count: number }[]): Changes | null {
  if (changes.length === 0) return null;
  const count = (name: string) => changes.find((c) => c.change === name)?.count ?? 0;
  return { added: count('new'), dropped: count('dropped') };
}
