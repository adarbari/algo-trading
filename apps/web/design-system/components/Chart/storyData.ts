/**
 * Deterministic sample data for the Chart stories and tests: seeded random walks over weekdays
 * from 30 Sep 2024 to 2 Oct 2026, ending on fixed closes, with sample events and volume. Not
 * market data.
 */
import type { ChartBand, ChartEvent, ChartPoint, ChartSeries } from './chartData';

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
