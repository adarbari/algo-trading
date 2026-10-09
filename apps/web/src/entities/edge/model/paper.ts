/**
 * The paper record as the pages show it (ADR 0053 amendment 2026-10-09): the types of the served
 * `edgeDesk` and `edgePaper`, the labels and tones of the served record states and trade statuses,
 * and the picture's bars and markers laid out as the distribution component takes them. Every
 * number and sentence is the read model's; this only names codes and maps served values.
 */
import type { DistributionBin, DistributionMarker, StatusTone } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

type Desk = NonNullable<gqlTypes.EdgeDeskQuery['edgeDesk']>;
export type DeskTrade = Desk['buys'][number];
export type FollowedEdge = Desk['followed'][number];
export type EdgePaper = NonNullable<gqlTypes.EdgePaperQuery['edgePaper']>;
export type PaperRecord = EdgePaper['record'];
export type PaperTrade = EdgePaper['trades'][number];
export type ForwardTest = NonNullable<EdgePaper['forward']>;

const RECORD_LABELS: Record<string, string> = {
  on_track: 'On track',
  below: 'Below the usual range',
  above: 'Above the usual range',
  too_early: 'Too early to judge',
  no_backtest: 'No backtest to compare',
  no_trades: 'No trades yet',
};

const RECORD_TONES: Record<string, StatusTone> = {
  on_track: 'positive',
  below: 'negative',
  above: 'info',
  too_early: 'neutral',
  no_backtest: 'neutral',
  no_trades: 'neutral',
};

export const recordLabel = (state: string): string => RECORD_LABELS[state] ?? state;

export const recordTone = (state: string): StatusTone => RECORD_TONES[state] ?? 'neutral';

const TRADE_LABELS: Record<string, string> = {
  open: 'Open',
  won: 'Won',
  lost: 'Lost',
  skipped: 'Skipped',
};

const TRADE_TONES: Record<string, StatusTone> = {
  open: 'info',
  won: 'positive',
  lost: 'negative',
  skipped: 'neutral',
};

export const tradeLabel = (status: string): string => TRADE_LABELS[status] ?? status;

export const tradeTone = (status: string): StatusTone => TRADE_TONES[status] ?? 'neutral';

const TONIGHT_LABELS: Record<string, string> = {
  signalled: 'Signalled',
  no_picks: 'No picks',
  not_due: 'Not due',
  skipped: 'Skipped',
  not_run: 'Not run',
};

const TONIGHT_TONES: Record<string, StatusTone> = {
  signalled: 'positive',
  no_picks: 'neutral',
  not_due: 'neutral',
  skipped: 'warning',
  not_run: 'warning',
};

/** What the nightly did for a followed edge on the session, as the signals table words it. */
export const tonightLabel = (state: string): string => TONIGHT_LABELS[state] ?? state;

export const tonightTone = (state: string): StatusTone => TONIGHT_TONES[state] ?? 'neutral';

/** The picture's bars: the chance the live win rate falls in each range. */
export function rangeBins(record: PaperRecord): DistributionBin[] {
  return record.bins.map((b) => ({ start: b.start, end: b.end, count: b.chance }));
}

/** The picture's lines: the live win rate and the two ends of the usual range, when served. */
export function rangeMarkers(record: PaperRecord): DistributionMarker[] {
  return [
    ...(record.winRate == null
      ? []
      : [{ value: record.winRate, label: 'Live', tone: 'accent' as const }]),
    ...(record.low == null ? [] : [{ value: record.low, label: 'Range start' }]),
    ...(record.high == null ? [] : [{ value: record.high, label: 'Range end' }]),
  ];
}
