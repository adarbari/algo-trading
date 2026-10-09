/**
 * The paper record as the pages show it (ADR 0053 amendment 2026-10-09): the types of the served
 * `edgeDesk` and `edgePaper`, the labels and tones of the served record states and trade statuses,
 * and the picture's bars and markers laid out as the distribution component takes them. Every
 * number and sentence is the read model's; this only names codes and maps served values.
 */
import type { DistributionBin, DistributionMarker, StatusTone } from '@algotrade/ui';

interface Side {
  closed: number;
  wins: number;
  winRate: number | null;
}

export interface DeskTrade {
  edgeId: string;
  edgeName: string;
  instrumentId: string;
  rank: number;
  buySession: string;
  sellSession: string;
  instrument: { symbol: string } | null;
}

export interface FollowedEdge {
  edgeId: string;
  name: string;
  state: string;
  tonight: string;
  tonightReason: string;
  missed: string[];
  record: { state: string; closed: number; open: number; winRate: number | null };
}

export interface Desk {
  session: string;
  sellSession: string;
  buys: DeskTrade[];
  sells: DeskTrade[];
  followed: FollowedEdge[];
}

export interface PaperRecord {
  state: string;
  closed: number;
  wins: number;
  open: number;
  skipped: number;
  winRate: number | null;
  backtestRate: number | null;
  basis: string;
  low: number | null;
  high: number | null;
  headline: string;
  bins: { start: number; end: number; chance: number }[];
}

export interface PaperTrade {
  instrumentId: string;
  rank: number;
  signalSession: string;
  buySession: string;
  sellSession: string;
  status: string;
  reason: string;
  excessReturn: number | null;
  instrument: { symbol: string } | null;
}

export interface ForwardTest {
  replaces: string;
  replacesName: string;
  since: string;
  sessions: number;
  needed: number;
  headline: string;
  this: Side;
  replaced: Side;
}

export interface EdgePaper {
  record: PaperRecord;
  trades: PaperTrade[];
  forward: ForwardTest | null;
}

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
