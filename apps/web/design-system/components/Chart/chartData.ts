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
  /** The value; `null` is a gap: the line breaks there (no value that day, not a zero). */
  value: number | null;
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

export type ChartEventKind = 'dividend' | 'split' | 'earnings' | 'filing' | 'macro';

export interface ChartEvent {
  time: string;
  kind: ChartEventKind;
  /**
   * Short text for the tooltip and table: the amount or ratio ("$0.26", "4-for-1"), the time
   * ("after close"), or for a filing or a macro release what it is ("8-K 2.02 results", "CPI 08:30").
   */
  detail?: string;
}

/** The tones a band, lane segment or reference line takes: the StatusBadge tones. */
export type ChartTone = StatusTone;

/** The tones a shaded band takes (`accent` is the one accent hue). */
export type ChartBandTone = ChartTone;

export interface ChartBand {
  /** First day of the span, ISO. A non-trading day shades from the next day with data. */
  start: string;
  /** Last day of the span, ISO (inclusive). */
  end: string;
  /** Tint of the span. */
  tone: ChartBandTone;
  /** What the span is ("Stress"): its name for assistive technology, the key and the table. */
  label: string;
  /**
   * `solid` (default) tint, or `hatch`: diagonal lines in the tone, so overlapping spans stay
   * readable and colour is not the only signal (recessions).
   */
  pattern?: 'solid' | 'hatch';
}

/**
 * A horizontal span of values across the price pane (the criterion's passing zone, a normal
 * range). An absent `from` runs to the bottom of the pane, an absent `to` to the top.
 */
export interface ChartValueBand {
  /** Lower edge, on the axis' scale; absent: open below. */
  from?: number;
  /** Upper edge; absent: open above. */
  to?: number;
  /** Tint of the span. */
  tone: ChartBandTone;
  /** What the span is ("Squeeze zone"): its name for assistive technology and the key. */
  label: string;
}

/** A horizontal line across the price pane at a value: a threshold, a target, a baseline. */
export interface ChartReferenceLine {
  /** Where the line sits, on the axis' scale (the value as drawn, so rebased when `rebase`). */
  value: number;
  /** Its name ("Inversion"), drawn at the right end of the line and read to screen readers. */
  label?: string;
  /** Colour of the line (default `neutral`). */
  tone?: ChartTone;
  /** Dashed instead of solid (default false). */
  dash?: boolean;
}

/** One span of a lane: a start and end day (inclusive), a tone and an optional name. */
export interface ChartLaneSegment {
  start: string;
  end: string;
  tone: ChartTone;
  /** What the span is ("Inverted"): the hover title, the key and the screen-reader list. */
  label?: string;
}

/** A thin strip under the x axis: a state over time (one lane per row). */
export interface ChartLane {
  /** Stable key. */
  id: string;
  /** The row's name ("Yield curve"), written above its strip. */
  label: string;
  segments: readonly ChartLaneSegment[];
}

/** Marker key: a shape and a letter per kind, so colour is never the only key. */
export const EVENT_KINDS: Record<ChartEventKind, { label: string; letter: string }> = {
  dividend: { label: 'Ex-dividend', letter: 'D' },
  split: { label: 'Split', letter: 'S' },
  earnings: { label: 'Earnings', letter: 'E' },
  filing: { label: 'Filing', letter: 'F' },
  macro: { label: 'Macro release', letter: 'M' },
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

/** An event on a non-trading day (or in a gap) sits on the next day with a value (or the last one). */
export function snapToData(time: string, points: readonly ChartPoint[]): string | undefined {
  const valued = points.filter((p) => p.value !== null);
  return (valued.find((p) => p.time >= time) ?? valued.at(-1))?.time;
}

/** Each value as a multiple of the first one, x 100. */
export function rebased(points: readonly ChartPoint[]): ChartPoint[] {
  const base = points.find(
    (p) => p.value !== null && Number.isFinite(p.value) && p.value !== 0,
  )?.value;
  if (base === undefined || base === null) return [];
  return points.map((p) => ({
    time: p.time,
    value: p.value === null ? null : (p.value / base) * 100,
  }));
}

export interface PreparedSeries extends ChartSeries {
  tone: Series;
}

export interface PreparedChart {
  series: PreparedSeries[];
  events: ChartEvent[];
  bands: ChartBand[];
  referenceLines: ChartReferenceLine[];
  valueBands: ChartValueBand[];
  lanes: ChartLane[];
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
    referenceLines?: readonly ChartReferenceLine[];
    valueBands?: readonly ChartValueBand[];
    lanes?: readonly ChartLane[];
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
    series: prepared.filter((s) => s.points.some((p) => p.value !== null)),
    events: inWindow(options.events ?? [], start).filter((e) => last === null || e.time <= last),
    bands: clampBands(options.bands ?? [], first, end),
    referenceLines: (options.referenceLines ?? []).filter((l) => Number.isFinite(l.value)),
    valueBands: (options.valueBands ?? []).filter(isValueBand),
    lanes: (options.lanes ?? []).map((lane) => ({
      ...lane,
      segments: clampBands(lane.segments, first, end),
    })),
    volume: inWindow(options.volume ?? [], start),
    start: first,
    end,
  };
}

/** A value band with at least one finite edge, the lower not above the upper. */
function isValueBand(b: ChartValueBand): boolean {
  const low = b.from === undefined ? -Infinity : b.from;
  const high = b.to === undefined ? Infinity : b.to;
  return (
    !Number.isNaN(low) && !Number.isNaN(high) && low <= high && (low > -Infinity || high < Infinity)
  );
}

/** The spans (bands, lane segments) that overlap the window, cut to its first and last day, oldest first. */
export function clampBands<T extends { start: string; end: string }>(
  bands: readonly T[],
  first: string | null,
  last: string | null,
): T[] {
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
  band: { start: string; end: string },
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
    // Gaps (null) are skipped: the first and last value, and the extremes, are of what is drawn.
    const known = s.points.filter((p): p is { time: string; value: number } => p.value !== null);
    const first = known[0];
    const last = known.at(-1);
    if (!first || !last) continue;
    const values = known.map((p) => p.value);
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
  if (chart.referenceLines.length > 0) {
    const lines = chart.referenceLines.map((l) =>
      [l.label, value(l.value)].filter(Boolean).join(' '),
    );
    parts.push(`reference lines: ${lines.join(', ')}`);
  }
  if (chart.valueBands.length > 0) {
    const zones = chart.valueBands.map((b) => `${b.label} ${describeValueBand(b, value)}`);
    parts.push(
      `shaded value ${chart.valueBands.length === 1 ? 'zone' : 'zones'}: ${zones.join(', ')}`,
    );
  }
  if (chart.lanes.length > 0) {
    parts.push(`lanes under the axis: ${chart.lanes.map((l) => l.label).join(', ')}`);
  }
  return `${parts.join('; ')}.`;
}

/** "from 0 to 0.1", "at or above 5" style text of a value band's extent. */
export function describeValueBand(band: ChartValueBand, value: (v: number) => string): string {
  if (band.from !== undefined && band.to !== undefined) {
    return `from ${value(band.from)} to ${value(band.to)}`;
  }
  return band.from !== undefined ? `above ${value(band.from)}` : `below ${value(band.to ?? 0)}`;
}

/** One row of the table fallback: a day with each series' value, volume and events. */
export interface ChartTableRow {
  time: string;
  values: Record<string, number | undefined>;
  volume: number | undefined;
  events: string;
  /** Labels of the bands covering the day, joined. */
  shaded: string;
  /** Per lane id: the label of the segment covering the day ("" when none). */
  lanes: Record<string, string>;
}

/** Newest first, every day any series has a value. */
export function tableRows(chart: PreparedChart): ChartTableRow[] {
  const byTime = new Map<string, ChartTableRow>();
  const row = (time: string) => {
    let found = byTime.get(time);
    if (!found) {
      found = { time, values: {}, volume: undefined, events: '', shaded: '', lanes: {} };
      byTime.set(time, found);
    }
    return found;
  };
  for (const s of chart.series)
    for (const p of s.points) row(p.time).values[s.id] = p.value ?? undefined;
  for (const v of chart.volume) {
    if (byTime.has(v.time)) row(v.time).volume = v.value ?? undefined;
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
    for (const lane of chart.lanes) {
      r.lanes[lane.id] = lane.segments
        .filter((g) => r.time >= g.start && r.time <= g.end)
        .map((g) => g.label ?? '')
        .filter(Boolean)
        .join('; ');
    }
  }
  return [...byTime.values()].sort((a, b) => (a.time < b.time ? 1 : -1));
}
