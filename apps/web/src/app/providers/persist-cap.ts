/**
 * What the persisted page cache may hold and how much of it: which queries are worth keeping
 * between visits (GraphQL page reads, never live, polled or preview reads) and the record that
 * fits the byte cap, least recently used queries dropped first. Pure: no storage, no clock.
 */

/** The hard cap on the serialized record in the browser's storage (owner decision 2026-10-09). */
export const CACHE_CAP_BYTES = 10 * 1024 * 1024;

/** Room kept for the record's envelope (version, stamps, brackets) inside the cap. */
const ENVELOPE_BYTES = 1024;

/**
 * GraphQL operations never persisted: who is signed in (always asked again), live option
 * quotes, and the admin reads that poll a running job or show a state that changes by the minute.
 */
const NEVER_PERSISTED = new Set([
  'Viewer',
  'SessionDate',
  'OptionQuotes',
  'OptionChain',
  'NightlyRuns',
  'RunItems',
  'RunRecord',
  'StatusScreens',
  'IngestionCompleteness',
  'IngestionCell',
  'HarnessRun',
  'HarnessRuns',
  'LlmUsage',
  'Verification',
  'QualityChecks',
]);

/** A query as stored: what `dehydrate` gives, the part this module reads. */
export interface StoredQuery {
  queryHash: string;
  queryKey: readonly unknown[];
  state: { dataUpdatedAt: number };
}

/**
 * Whether a query with this key may be kept: only `['gql', <operation>, ...]` reads (REST reads
 * are writes, jobs, polling, previews and live quotes) and not the operations above.
 */
export function isPersistableKey(key: readonly unknown[]): boolean {
  return key[0] === 'gql' && typeof key[1] === 'string' && !NEVER_PERSISTED.has(key[1]);
}

/** The bytes of `text` in UTF-8, which is what the browser stores (not `text.length`). */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

export interface Fitted {
  /** The queries kept, as one JSON array text, most recently used first. */
  queriesJson: string;
  kept: number;
  dropped: number;
}

/**
 * The queries that fit under `cap` bytes together with the record's envelope: sorted by last
 * use (`lastUsed` hash -> ms, else the time the data arrived), the oldest dropped first. One
 * query bigger than the cap alone is dropped and never evicts the others.
 */
export function fitToCap(
  queries: readonly StoredQuery[],
  lastUsed: ReadonlyMap<string, number>,
  cap: number = CACHE_CAP_BYTES,
): Fitted {
  const used = (q: StoredQuery) => lastUsed.get(q.queryHash) ?? q.state.dataUpdatedAt;
  const recent = [...queries].sort((a, b) => used(b) - used(a));
  const budget = cap - ENVELOPE_BYTES;
  const parts: string[] = [];
  let bytes = 2; // the array's brackets
  for (const query of recent) {
    const text = JSON.stringify(query);
    const size = byteLength(text) + 1; // and its comma
    if (size > budget) continue;
    // The rest are older: the first that no longer fits ends the list.
    if (bytes + size > budget) break;
    parts.push(text);
    bytes += size;
  }
  return {
    queriesJson: `[${parts.join(',')}]`,
    kept: parts.length,
    dropped: queries.length - parts.length,
  };
}
