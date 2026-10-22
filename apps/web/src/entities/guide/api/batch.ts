/**
 * The Guide's batched read (ADR 0051, ADR 0037): every help button of a page asks for its entry
 * on mount, so a page of twenty buttons made twenty requests. Each `load*` call here waits a
 * few milliseconds, then all the entries asked in that window (an indicator, an episode, a
 * term, a Start here page) go to the API as one `Query.guideEntries` operation, and each caller
 * gets exactly what its single-entry query would have returned. The hooks keep their own query
 * keys, so a drawer, a card's button and a full page share one cache entry per entry.
 */
import { gql, graphql, type gqlTypes } from '@/shared/api';

/** How long a read waits for the others of its page (they are issued in one render). */
const WINDOW_MS = 5;

// Each selection is the same as the single-entry query it stands in for (hooks.ts): the answer
// is cached under that query's key, so the two must stay in step (the batch test checks it).
const GuideEntriesQuery = graphql(`
  query GuideEntries($refs: [GuideRef!]!) {
    guideEntries(refs: $refs) {
      indicators {
        key
        plainName
        technicalName
        pace
        summary {
          segments {
            text
            field
          }
        }
        whyItMatters {
          segments {
            text
            field
          }
        }
        whatOnMeans {
          segments {
            text
            field
          }
        }
        leadTime {
          segments {
            text
            field
          }
        }
        trackRecord {
          segments {
            text
            field
          }
        }
        before {
          label
          episode
          line {
            segments {
              text
              field
            }
          }
        }
        how {
          text
          url
        }
        feature
        sources {
          title
          url
        }
      }
      episodes {
        episode {
          key
          name
          kind
          peak
          trough
          recovered
          spxDrawdown
          nasdaqDrawdown
          recession
          nberStart
          nberEnd
          knownFrom
        }
        cause {
          segments {
            text
            field
          }
        }
        notes {
          segments {
            text
            field
          }
        }
        indicators {
          key
          plainName
          label
          line {
            segments {
              text
              field
            }
          }
        }
      }
      terms {
        entry {
          id
          term
          short
        }
        body {
          segments {
            text
            field
          }
        }
        seeAlso {
          id
          term
          short
        }
      }
      startPages {
        entry {
          id
          order
          title
          summary
        }
        sections {
          title
          body {
            segments {
              text
              field
            }
          }
        }
        links {
          kind
          id
          title
        }
      }
    }
  }
`);

type Kind = gqlTypes.GuideEntryKind;
type Entries = NonNullable<gqlTypes.GuideEntriesQuery['guideEntries']>;

interface Waiting {
  ref: gqlTypes.GuideRef;
  settle: ((entries: Entries) => void)[];
  fail: ((error: unknown) => void)[];
}

let waiting = new Map<string, Waiting>();
let timer: ReturnType<typeof setTimeout> | undefined;

/** The API refuses more refs than this in one read (`MAX_REFS`): a larger page is several. */
const MAX_REFS = 100;

async function readChunk(chunk: readonly Waiting[]): Promise<void> {
  try {
    const { guideEntries } = await gql(GuideEntriesQuery, { refs: chunk.map((w) => w.ref) });
    const entries: Entries = guideEntries ?? {
      indicators: [],
      episodes: [],
      terms: [],
      startPages: [],
    };
    for (const w of chunk)
      w.settle.forEach((settle) => {
        settle(entries);
      });
  } catch (error) {
    for (const w of chunk)
      w.fail.forEach((fail) => {
        fail(error);
      });
  }
}

async function flush(): Promise<void> {
  const asked = [...waiting.values()];
  waiting = new Map();
  timer = undefined;
  const chunks: Waiting[][] = [];
  for (let i = 0; i < asked.length; i += MAX_REFS) chunks.push(asked.slice(i, i + MAX_REFS));
  await Promise.all(chunks.map(readChunk));
}

/** One entry's answer out of the batch (null: the Guide has no such entry). */
function load<T>(kind: Kind, id: string, pick: (entries: Entries) => T): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const key = `${kind}:${id}`;
    const slot = waiting.get(key) ?? { ref: { kind, id }, settle: [], fail: [] };
    slot.settle.push((entries) => {
      resolve(pick(entries));
    });
    slot.fail.push(reject);
    waiting.set(key, slot);
    timer ??= setTimeout(() => void flush(), WINDOW_MS);
  });
}

/** `Query.guideIndicator`'s answer for `key`, read in the page's batch. */
export function loadIndicator(
  key: string,
): Promise<{ guideIndicator: Entries['indicators'][number] | null }> {
  return load('INDICATOR', key, (e) => ({
    guideIndicator: e.indicators.find((i) => i.key === key) ?? null,
  }));
}

/** `Query.guideEpisode`'s answer for `slug`, read in the page's batch. */
export function loadEpisode(
  slug: string,
): Promise<{ guideEpisode: Entries['episodes'][number] | null }> {
  return load('EPISODE', slug, (e) => ({
    guideEpisode: e.episodes.find((x) => x.episode.key === slug) ?? null,
  }));
}

/** `Query.guideTerm`'s answer for `id`, read in the page's batch. */
export function loadTerm(id: string): Promise<{ guideTerm: Entries['terms'][number] | null }> {
  return load('TERM', id, (e) => ({
    guideTerm: e.terms.find((t) => t.entry.id === id) ?? null,
  }));
}

/** `Query.guideStartPage`'s answer for `id`, read in the page's batch. */
export function loadStartPage(
  id: string,
): Promise<{ guideStartPage: Entries['startPages'][number] | null }> {
  return load('START', id, (e) => ({
    guideStartPage: e.startPages.find((p) => p.entry.id === id) ?? null,
  }));
}
