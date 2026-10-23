/**
 * The stored dividends, splits and earnings as rows of the event list under the price chart,
 * oldest first: one per kind and day, each described in words with its source page where the
 * server sent one. A day with a report from the calendar and one from the company's own 8-K
 * (the server's `confirmed` row, ADR 0050 decision 3) shows the 8-K's, whether or not its
 * filing page was found. Its own module, loaded with the list and not with the chart.
 */
import type { ChartEvent, ChartEventPart } from '@algotrade/ui';

import type { EventRow } from '../api/eventList';
import { toTimeline } from '@/entities/instrument';

const SHOWN = new Set(['dividend', 'split', 'earnings']);
const WORDS: Readonly<Record<string, (detail: string) => string>> = {
  dividend: (detail) => `Ex-dividend ${detail}`,
  split: (detail) => `Split ${detail}`,
  earnings: (detail) => (detail ? `Earnings, ${detail}` : 'Earnings'),
};

export function storedEventRows(events: readonly EventRow[]): ChartEvent[] {
  const chosen = new Map<string, EventRow>();
  for (const e of events) {
    if (!SHOWN.has(e.kind)) continue;
    const key = `${e.kind}|${e.date}`;
    const held = chosen.get(key);
    if (held === undefined || (!held.confirmed && e.confirmed)) chosen.set(key, e);
  }
  const picked = [...chosen.values()];
  const pages = new Map(picked.map((e) => [`${e.kind}|${e.date}`, e.sourceUrl]));
  return toTimeline(picked)
    .flatMap((t): ChartEvent[] => {
      const words = WORDS[t.kind];
      if (words === undefined) return [];
      const href = pages.get(`${t.kind}|${t.date}`);
      const part: ChartEventPart = href
        ? { text: words(t.detail), href }
        : { text: words(t.detail) };
      return [{ time: t.date, kind: t.kind as 'dividend' | 'split' | 'earnings', parts: [part] }];
    })
    .reverse();
}
