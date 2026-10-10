/** The summary of step 6: the user's own choices in one line each (no figure is derived). Pure. */
import type { EdgeDraft } from './draft';
import { EVENTS } from './options';

export interface SummaryLine {
  label: string;
  value: string;
}

const eventLabel = (event: string) => EVENTS.find((e) => e.value === event)?.label ?? event;

export function summaryOf(draft: EdgeDraft): SummaryLine[] {
  const when =
    draft.schedule === 'on_event'
      ? eventLabel(draft.event)
      : draft.schedule === 'month_end'
        ? 'Every month end'
        : 'Every session';
  const take = draft.take === 'all' ? 'all that qualify' : `top ${String(draft.topK ?? '?')}`;
  const win =
    draft.win === 'beats'
      ? 'beats SPY'
      : draft.win === 'rises'
        ? 'rises'
        : 'as the edge defines it';
  const held = [...draft.horizons].sort((a, b) => a - b).join(' / ');
  return [
    { label: 'Screens', value: draft.screeners.join(', ') || 'none chosen' },
    { label: 'Picks', value: `${when} · ${take}` },
    {
      label: 'Trade',
      value: `enter ${String(draft.startOffset ?? '?')} session(s) after · hold ${held || '?'} days · ${draft.costBps === null ? 'costs as the edge has them' : `${String(draft.costBps)} bps`} · win = ${win}`,
    },
    {
      label: 'Compare',
      value: `${draft.universe || 'its own universe'} · against ${draft.baselines.join(', ') || 'no baselines'}`,
    },
    { label: 'Out-of-sample', value: draft.frozenFrom ? `from ${draft.frozenFrom}` : 'none' },
  ];
}
