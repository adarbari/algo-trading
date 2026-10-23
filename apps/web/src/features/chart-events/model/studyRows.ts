/**
 * The event study's own earnings and macro dates ahead and its 8-Ks as rows of the event list
 * under the price chart, oldest first: one row a day for the filings (each 8-K its own link),
 * a macro release linked to its agency page, both as the server sent them (an upcoming earnings
 * date has no page). Earnings dates the stored events already show are left to them. Its own
 * module, loaded with the list and not with the chart.
 */
import { timeText, type ChartEvent, type ChartEventPart } from '@algotrade/ui';

import type { EventStudyLinks as Study } from '../api/eventList';

const part = (text: string, href: string | null | undefined): ChartEventPart =>
  href ? { text, href } : { text };

export function studyEventRows(study: Study, alreadyMarked: ReadonlySet<string>): ChartEvent[] {
  const ahead = study.ahead.flatMap((e): ChartEvent[] => {
    if (e.kind === 'own_earnings' && !alreadyMarked.has(e.date)) {
      return [
        { time: e.date, kind: 'earnings', parts: [{ text: `Earnings, ${timeText(e.time)}` }] },
      ];
    }
    if (e.kind === 'macro_release') {
      return [{ time: e.date, kind: 'macro', parts: [part(`${e.label} ${e.time}`, e.sourceUrl)] }];
    }
    return [];
  });
  const byDay = new Map<string, ChartEventPart[]>();
  for (const f of study.filings) {
    byDay.set(f.filingDate, [
      ...(byDay.get(f.filingDate) ?? []),
      part(`${f.form} ${f.label}`, f.sourceUrl),
    ]);
  }
  const filings = [...byDay].map(([time, parts]): ChartEvent => ({ time, kind: 'filing', parts }));
  return [...filings, ...ahead].sort((a, b) => a.time.localeCompare(b.time));
}
