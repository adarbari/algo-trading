/**
 * Deterministic sample data for the Chart stories and tests: seeded random walks over weekdays
 * from 30 Sep 2024 to 2 Oct 2026, ending on fixed closes, with sample events and volume. Not
 * market data.
 */
import type {
  ChartBand,
  ChartEvent,
  ChartLane,
  ChartPoint,
  ChartReferenceLine,
  ChartValueBand,
  ChartSeries,
} from './chartData';

/** Seeded PRNG (mulberry32): the same numbers on every run, so screenshots are stable. */
function random(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Weekdays (ISO) from `start` to `end` inclusive. */
export function weekdays(start: string, end: string): string[] {
  const days: string[] = [];
  const date = new Date(`${start}T00:00:00Z`);
  const stop = new Date(`${end}T00:00:00Z`);
  while (date <= stop) {
    const dow = date.getUTCDay();
    if (dow !== 0 && dow !== 6) days.push(date.toISOString().slice(0, 10));
    date.setUTCDate(date.getUTCDate() + 1);
  }
  return days;
}

export const DAYS = weekdays('2024-09-30', '2026-10-02');

/** A random walk over DAYS, scaled to end exactly on `last`. */
export function walk(seed: number, last: number, drift: number, vol: number): ChartPoint[] {
  const next = random(seed);
  let value = 100;
  const raw = DAYS.map((time) => {
    value *= 1 + drift + (next() - 0.5) * vol;
    return { time, value };
  });
  const scale = last / (raw.at(-1)?.value ?? 1);
  return raw.map((p) => ({ time: p.time, value: Math.round(p.value * scale * 100) / 100 }));
}

export const aapl: ChartSeries = {
  id: 'AAPL',
  label: 'AAPL',
  points: walk(7, 333.69, 0.0007, 0.032),
};
export const msft: ChartSeries = {
  id: 'MSFT',
  label: 'MSFT',
  points: walk(11, 512.4, 0.0004, 0.026),
};
export const nvda: ChartSeries = {
  id: 'NVDA',
  label: 'NVDA',
  points: walk(23, 187.3, 0.0012, 0.05),
};

export const aaplEvents: ChartEvent[] = [
  { time: '2024-11-08', kind: 'dividend', detail: '$0.25' },
  { time: '2025-01-30', kind: 'earnings', detail: 'after close' },
  { time: '2025-02-10', kind: 'dividend', detail: '$0.25' },
  { time: '2025-05-01', kind: 'earnings', detail: 'after close' },
  { time: '2025-05-12', kind: 'dividend', detail: '$0.26' },
  { time: '2025-06-16', kind: 'split', detail: '2-for-1 (sample)' },
  { time: '2025-07-31', kind: 'earnings', detail: 'after close' },
  { time: '2025-08-11', kind: 'dividend', detail: '$0.26' },
  { time: '2025-10-30', kind: 'earnings', detail: 'after close' },
  { time: '2025-11-10', kind: 'dividend', detail: '$0.26' },
  { time: '2026-01-29', kind: 'earnings', detail: 'after close' },
  { time: '2026-02-09', kind: 'dividend', detail: '$0.26' },
  { time: '2026-04-30', kind: 'earnings', detail: 'after close' },
  { time: '2026-05-11', kind: 'dividend', detail: '$0.27' },
  { time: '2026-07-30', kind: 'earnings', detail: 'after close' },
  { time: '2026-08-10', kind: 'dividend', detail: '$0.27' },
];

/** Earnings, the 8-K that reports them, and macro releases: the markers of the event-sensitivity price chart. */
export const eventMarkers: ChartEvent[] = [
  { time: '2025-10-30', kind: 'earnings', detail: 'after close' },
  { time: '2025-10-30', kind: 'filing', detail: '8-K 2.02 results' },
  { time: '2025-12-10', kind: 'macro', detail: 'FOMC 14:00' },
  { time: '2026-01-29', kind: 'earnings', detail: 'after close' },
  { time: '2026-01-29', kind: 'filing', detail: '8-K 2.02 results' },
  { time: '2026-03-18', kind: 'macro', detail: 'FOMC 14:00' },
  { time: '2026-04-30', kind: 'earnings', detail: 'after close' },
  { time: '2026-05-12', kind: 'macro', detail: 'CPI 08:30' },
  { time: '2026-06-10', kind: 'macro', detail: 'CPI 08:30' },
  { time: '2026-07-30', kind: 'earnings', detail: 'after close' },
  { time: '2026-07-30', kind: 'filing', detail: '8-K 2.02 results' },
  { time: '2026-09-16', kind: 'filing', detail: '8-K 5.02 management' },
];

export const aaplVolume: ChartPoint[] = (() => {
  const next = random(5);
  return DAYS.map((time) => ({ time, value: Math.round(38e6 + next() * 52e6) }));
})();

export const cautionBand: ChartBand = {
  start: '2026-01-12',
  end: '2026-02-20',
  tone: 'warning',
  label: 'Caution',
};
/** Starts on a Saturday: its first session is the Monday after. */
export const stressBand: ChartBand = {
  start: '2026-02-21',
  end: '2026-03-27',
  tone: 'negative',
  label: 'Stress',
};

/** Sample shaded periods (two cautions and a stress) over the last year. Not market data. */
export const sampleBands: ChartBand[] = [
  cautionBand,
  stressBand,
  { start: '2026-08-03', end: '2026-09-04', tone: 'warning', label: 'Caution' },
];

/** A hatched band that overlaps the caution and stress bands: the overlap stays readable. */
export const hatchedBand: ChartBand = {
  start: '2026-02-02',
  end: '2026-04-10',
  tone: 'negative',
  label: 'Recession',
  pattern: 'hatch',
};

/** The sample close with a missing stretch (null): the line breaks there. Not market data. */
export const aaplWithGap: ChartSeries = {
  ...aapl,
  points: aapl.points.map((p) =>
    p.time >= '2026-05-04' && p.time <= '2026-06-12' ? { ...p, value: null } : p,
  ),
};

/** Sample reference lines (a floor and a target) around the sample price. Not market data. */
export const sampleReferenceLines: ChartReferenceLine[] = [
  { value: 300, label: 'Floor', tone: 'negative', dash: true },
  { value: 340, label: 'Target', tone: 'positive' },
];

/** A sample value band: the zone under the sample floor, open below. Not market data. */
export const sampleValueBands: ChartValueBand[] = [
  { to: 300, tone: 'accent', label: 'Below the floor' },
];

/** Sample lanes: a state over time in two rows (labelled and unlabelled spans). Not market data. */
export const sampleLanes: ChartLane[] = [
  {
    id: 'trend',
    label: 'Trend',
    segments: [
      { start: '2025-10-02', end: '2026-01-09', tone: 'positive', label: 'Rising' },
      { start: '2026-01-12', end: '2026-03-27', tone: 'negative', label: 'Falling' },
      { start: '2026-03-30', end: '2026-10-02', tone: 'positive', label: 'Rising' },
    ],
  },
  {
    id: 'volatility',
    label: 'Volatility',
    segments: [
      { start: '2026-02-02', end: '2026-04-10', tone: 'warning', label: 'Elevated' },
      { start: '2026-08-03', end: '2026-09-04', tone: 'warning', label: 'Elevated' },
    ],
  },
];
