/**
 * Chart data shaping, pure and library-free: the public data types, time-range windows,
 * rebasing to 100, the accessible text summary and the rows of the "view as table" fallback.
 * Dates are ISO calendar days (`2026-10-02`), compared as strings.
 */
import { formatValue, type ValueFormat } from '../../format';
import { SERIES, type Series } from '../../tokens';
import type { StatusTone } from '../StatusBadge';

/** The time windows a caller offers (usually through a SegmentedControl). */
export type ChartRange = '3M' | '1Y' | '2Y' | 'All';

export const CHART_RANGES: readonly ChartRange[] = ['3M', '1Y', '2Y', 'All'];

export interface ChartPoint {
  /** ISO calendar day, `2026-10-02`. */
  time: string;
  value: number;
}

export interface ChartSeries {
  /** Stable id (keeps its colour when other series come and go). */
  id: string;
  /** Legend, tooltip and summary name ("AAPL"). */
  label: string;
  /** Oldest first. */
  points: readonly ChartPoint[];
  /** Series colour `s1`-`s6`; defaults to the series' position. */
  tone?: Series;
}

export type ChartEventKind = 'dividend' | 'split' | 'earnings';

export interface ChartEvent {
  time: string;
  kind: ChartEventKind;
  /** Short detail for the tooltip and table ("$0.26", "4-for-1", "after close"). */
  detail?: string;
}

/** The tones a shaded band takes: the StatusBadge tones (`accent` is the one accent hue). */
export type ChartBandTone = StatusTone;

export interface ChartBand {
  /** First day of the span, ISO. A non-trading day shades from the next day with data. */
  start: string;
  /** Last day of the span, ISO (inclusive). */
  end: string;
  /** Tint of the span. */
  tone: ChartBandTone;
  /** What the span is ("Stress"): its name for assistive technology, the key and the table. */
  label: string;
}

/** Marker key: a shape and a letter per kind, so colour is never the only key. */
export const EVENT_KINDS: Record<ChartEventKind, { label: string; letter: string }> = {
  dividend: { label: 'Ex-dividend', letter: 'D' },
  split: { label: 'Split', letter: 'S' },
  earnings: { label: 'Earnings', letter: 'E' },
};

const MONTHS: Record<ChartRange, number | null> = { '3M': 3, '1Y': 12, '2Y': 24, All: null };

/** The first day inside `range`, counted back from `last` (ISO day); null for All. */
export function rangeStart(last: string, range: ChartRange): string | null {
  const months = MONTHS[range];
  if (months === null) return null;
  const date = new Date(`${last}T00:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() - months);
  return date.toISOString().slice(0, 10);
}

/** The latest day across all series. */
export function lastTime(series: readonly ChartSeries[]): string | null {
  let last: string | null = null;
  for (const s of series) {
    const t = s.points.at(-1)?.time;
    if (t !== undefined && (last === null || t > last)) last = t;
  }
  return last;
}

/** Points on or after `start` (all when null). */
export function inWindow<T extends { time: string }>(points: readonly T[], start: string | null) {
  return start === null ? [...points] : points.filter((p) => p.time >= start);
}

/** An event on a non-trading day sits on the next day with data (or the last one). */
export function snapToData(time: string, points: readonly ChartPoint[]): string | undefined {
  return (points.find((p) => p.time >= time) ?? points.at(-1))?.time;
}

/** Each value as a multiple of the first one, x 100. */
export function rebased(points: readonly ChartPoint[]): ChartPoint[] {
  const base = points.find((p) => Number.isFinite(p.value) && p.value !== 0)?.value;
  if (base === undefined) return [];
  return points.map((p) => ({ time: p.time, value: (p.value / base) * 100 }));
}

export interface PreparedSeries extends ChartSeries {
  tone: Series;
}

export interface PreparedChart {
  series: PreparedSeries[];
  events: ChartEvent[];
  bands: ChartBand[];
  volume: ChartPoint[];
  start: string | null;
  end: string | null;
}

/** Windows, rebases and colours the caller's data for drawing, the summary and the table. */
export function prepare(
  series: readonly ChartSeries[],
  options: {
    range: ChartRange;
    rebase: boolean;
    events?: readonly ChartEvent[];
    bands?: readonly ChartBand[];
    volume?: readonly ChartPoint[];
  },
): PreparedChart {
  const last = lastTime(series);
  const start = last === null ? null : rangeStart(last, options.range);
  const prepared = series.map((s, index) => {
    const points = inWindow(s.points, start);
    return {
      ...s,
      tone: s.tone ?? SERIES[index % SERIES.length] ?? 's1',
      points: options.rebase ? rebased(points) : points,
    };
  });
  const times = prepared.flatMap((s) => s.points.map((p) => p.time)).sort();
  const first = times[0] ?? null;
  const end = times.at(-1) ?? null;
  return {
    series: prepared.filter((s) => s.points.length > 0),
    events: inWindow(options.events ?? [], start).filter((e) => last === null || e.time <= last),
    bands: clampBands(options.bands ?? [], first, end),
    volume: inWindow(options.volume ?? [], start),
    start: first,
    end,
  };
}

/** The bands that overlap the window, cut to its first and last day, oldest first. */
export function clampBands(
  bands: readonly ChartBand[],
  first: string | null,
  last: string | null,
): ChartBand[] {
  if (first === null || last === null) return [];
  return bands
    .filter((b) => b.start <= b.end && b.end >= first && b.start <= last)
    .map((b) => ({
      ...b,
      start: b.start < first ? first : b.start,
      end: b.end > last ? last : b.end,
    }))
    .sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0));
}

/**
 * The first and last day WITH DATA a band covers (a band over a weekend or a holiday shades the
 * sessions inside it), or undefined when it holds no session.
 */
export function bandSpan(
  band: ChartBand,
  points: readonly ChartPoint[],
): { from: string; to: string } | undefined {
  const inside = points.filter((p) => p.time >= band.start && p.time <= band.end);
  const from = inside[0]?.time;
  const to = inside.at(-1)?.time;
  return from === undefined || to === undefined ? undefined : { from, to };
}

/** The text alternative: what is drawn, over which dates, and how each series moved. */
export function describeChart(
  label: string,
  chart: PreparedChart,
  options: { rebase: boolean; format: ValueFormat },
): string {
  if (chart.series.length === 0 || chart.start === null || chart.end === null) {
    return `${label}: no data.`;
  }
  const date = (t: string) => formatValue(t, { kind: 'date', style: 'short' }).text;
  const value = (v: number) => formatValue(v, options.format).text;
  const parts = [
    `${label}${options.rebase ? ', rebased to 100' : ''}, ${date(chart.start)} to ${date(chart.end)}`,
  ];
  for (const s of chart.series) {
    const first = s.points[0];
    const last = s.points.at(-1);
    if (!first || !last) continue;
    const values = s.points.map((p) => p.value);
    const change = formatValue(last.value / first.value - 1, { kind: 'delta', unit: 'percent' });
    parts.push(
      `${s.label} ${value(first.value)} to ${value(last.value)} (${change.text}), low ${value(Math.min(...values))}, high ${value(Math.max(...values))}`,
    );
  }
  if (chart.events.length > 0) {
    const counts = (Object.keys(EVENT_KINDS) as ChartEventKind[])
      .map((kind) => [kind, chart.events.filter((e) => e.kind === kind).length] as const)
      .filter(([, n]) => n > 0)
      .map(([kind, n]) => `${String(n)} ${EVENT_KINDS[kind].label.toLowerCase()}`);
    parts.push(`events: ${counts.join(', ')}`);
  }
  if (chart.bands.length > 0) {
    parts.push(
      `${String(chart.bands.length)} shaded ${chart.bands.length === 1 ? 'period' : 'periods'}`,
    );
  }
  return `${parts.join('; ')}.`;
}

/** One row of the table fallback: a day with each series' value, volume and events. */
export interface ChartTableRow {
  time: string;
  values: Record<string, number | undefined>;
  volume: number | undefined;
  events: string;
  /** Labels of the bands covering the day, joined. */
  shaded: string;
}

/** Newest first, every day any series has a value. */
export function tableRows(chart: PreparedChart): ChartTableRow[] {
  const byTime = new Map<string, ChartTableRow>();
  const row = (time: string) => {
    let found = byTime.get(time);
    if (!found) {
      found = { time, values: {}, volume: undefined, events: '', shaded: '' };
      byTime.set(time, found);
    }
    return found;
  };
  for (const s of chart.series) for (const p of s.points) row(p.time).values[s.id] = p.value;
  for (const v of chart.volume) {
    if (byTime.has(v.time)) row(v.time).volume = v.value;
  }
  for (const e of chart.events) {
    const r = row(e.time);
    const text = [EVENT_KINDS[e.kind].label, e.detail].filter(Boolean).join(' ');
    r.events = r.events ? `${r.events}; ${text}` : text;
  }
  for (const r of byTime.values()) {
    r.shaded = chart.bands
      .filter((b) => r.time >= b.start && r.time <= b.end)
      .map((b) => b.label)
      .join('; ');
  }
  return [...byTime.values()].sort((a, b) => (a.time < b.time ? 1 : -1));
}
