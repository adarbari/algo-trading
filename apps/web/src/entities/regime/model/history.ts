/**
 * The regime's history charts as `Chart` props (ADR 0047, RG7): a stored field over years
 * (`Market.history`) as lines with gaps where nothing is stored, the verdict flag and the regime
 * label as lanes under the lines, the coverage of the evidence as a lane, the episodes and NBER
 * recessions as shaded bands, a threshold as a dashed line. The server does the arithmetic (the
 * verdict, the label, the buckets); this file only maps what it sent to tones, labels and spans:
 * the signal on is warning, a fall (peak to trough) negative, a recovery positive, a recession
 * neutral and hatched, nothing stored neutral (`docs/ui/design-system.md`).
 */
import type {
  ChartBand,
  ChartLane,
  ChartLaneSegment,
  ChartPoint,
  ChartReferenceLine,
  ChartSeries,
} from '@algotrade/ui';

import { addDays } from '@/shared/lib/date';

import {
  plainLabel,
  regimeTone,
  storedLabel,
  type Recession,
  type RegimeEpisode,
  type RegimeLabel,
} from './regime';

/** One point of a numeric history: `value` null is a gap (no stored row), never a zero. */
export interface HistoryPoint {
  session: string;
  value: number | null;
}

/** Consecutive sessions `start..end` with one flag, label or UNKNOWN value. */
export interface HistorySegment {
  start: string;
  end: string;
  value: string;
}

/** One stored market field over a window (`Market.history`). */
export interface SeriesHistory {
  name: string;
  bucketSessions: number;
  points: readonly HistoryPoint[];
  segments: readonly HistorySegment[];
}

/** The days a chart covers, inclusive. */
export interface HistoryWindow {
  start: string;
  end: string;
}

/** The share of a score's weight known at which the evidence reads as full. */
export const FULL_EVIDENCE = 0.9;

export const BAND_LABELS = {
  fall: 'Market fall, peak to trough',
  recovery: 'Recovery, trough to new high',
  recession: 'NBER recession',
} as const;

export const LANE_LABELS = {
  signalOn: 'Signal on',
  noData: 'No data',
  fullEvidence: 'Full evidence',
  partialEvidence: 'Partial evidence',
  noEvidence: 'No evidence',
} as const;

/** A history's points as chart points, oldest first; a gap stays a null so the line breaks. */
export function toChartPoints(history: SeriesHistory | undefined): ChartPoint[] {
  return (history?.points ?? []).map((point) => ({ time: point.session, value: point.value }));
}

/** The lane of a verdict flag: ON spans warning, UNKNOWN neutral, OFF draws nothing. */
export function signalLane(verdict: SeriesHistory | undefined): ChartLane | null {
  if (verdict === undefined) return null;
  const segments = verdict.segments.flatMap((segment): ChartLaneSegment[] => {
    if (segment.value === 'ON') {
      return [
        { start: segment.start, end: segment.end, tone: 'warning', label: LANE_LABELS.signalOn },
      ];
    }
    if (segment.value === 'UNKNOWN') {
      return [
        { start: segment.start, end: segment.end, tone: 'neutral', label: LANE_LABELS.noData },
      ];
    }
    return [];
  });
  return { id: 'signal', label: 'Signal', segments };
}

/** The lane of the regime label: the weather word and its tone for each run of sessions. */
export function regimeLane(label: SeriesHistory | undefined): ChartLane | null {
  if (label === undefined) return null;
  const segments = label.segments.map((segment): ChartLaneSegment => {
    const stored: RegimeLabel = storedLabel(segment.value) ?? 'UNKNOWN';
    return {
      start: segment.start,
      end: segment.end,
      tone: regimeTone(stored),
      label: plainLabel(stored),
    };
  });
  return { id: 'regime', label: 'Regime', segments };
}

function evidenceOf(value: number | null): { tone: ChartLaneSegment['tone']; label: string } {
  if (value !== null && value >= FULL_EVIDENCE) {
    return { tone: 'info', label: LANE_LABELS.fullEvidence };
  }
  if (value !== null && value > 0) return { tone: 'warning', label: LANE_LABELS.partialEvidence };
  return { tone: 'neutral', label: LANE_LABELS.noEvidence };
}

/**
 * The lane of how much of a score's weight was known: full (at or above `FULL_EVIDENCE`),
 * partial, or none, each run of points one segment that runs up to the day before the next.
 */
export function evidenceLane(coverage: SeriesHistory | undefined): ChartLane | null {
  const points = coverage?.points ?? [];
  if (points.length === 0) return null;
  const runs: { start: string; evidence: ReturnType<typeof evidenceOf> }[] = [];
  for (const point of points) {
    const evidence = evidenceOf(point.value);
    if (runs.at(-1)?.evidence.label !== evidence.label)
      runs.push({ start: point.session, evidence });
  }
  const last = points.at(-1)?.session ?? '';
  const segments = runs.map(({ start, evidence }, index): ChartLaneSegment => {
    const next = runs[index + 1];
    return { start, end: next === undefined ? last : addDays(next.start, -1), ...evidence };
  });
  return { id: 'evidence', label: 'Evidence', segments };
}

const overlaps = (start: string, end: string, window: HistoryWindow): boolean =>
  end >= window.start && start <= window.end;

/**
 * The shaded periods of a window: each reference episode's fall (peak to trough, negative) and
 * recovery (trough to the new high, positive, only once it has come), and each NBER recession
 * (neutral, hatched, to the window's end while the committee has not dated its end).
 */
export function episodeBands(
  episodes: readonly RegimeEpisode[],
  recessions: readonly Recession[],
  window: HistoryWindow,
): ChartBand[] {
  const bands: ChartBand[] = [];
  for (const recession of recessions) {
    const end = recession.end ?? window.end;
    if (overlaps(recession.start, end, window)) {
      bands.push({
        start: recession.start,
        end,
        tone: 'neutral',
        label: BAND_LABELS.recession,
        pattern: 'hatch',
      });
    }
  }
  for (const episode of episodes) {
    if (overlaps(episode.peak, episode.trough, window)) {
      bands.push({
        start: episode.peak,
        end: episode.trough,
        tone: 'negative',
        label: BAND_LABELS.fall,
      });
    }
    if (episode.recovered !== null && overlaps(episode.trough, episode.recovered, window)) {
      bands.push({
        start: episode.trough,
        end: episode.recovered,
        tone: 'positive',
        label: BAND_LABELS.recovery,
      });
    }
  }
  return bands;
}

export interface SeriesInput {
  id: string;
  label: string;
  history: SeriesHistory | undefined;
}

export interface HistoryChartProps {
  series: ChartSeries[];
  lanes: ChartLane[];
  bands: ChartBand[];
  referenceLines: ChartReferenceLine[];
}

/**
 * Everything a regime history chart draws: the lines of `series`, the `lanes` that exist, the
 * episode and recession bands inside `window`, and a dashed line at `threshold` (null: none).
 */
export function toHistoryChart(input: {
  series: readonly SeriesInput[];
  lanes: readonly (ChartLane | null)[];
  threshold: { value: number; label: string } | null;
  episodes: readonly RegimeEpisode[];
  recessions: readonly Recession[];
  window: HistoryWindow;
}): HistoryChartProps {
  return {
    series: input.series.map((s) => ({
      id: s.id,
      label: s.label,
      points: toChartPoints(s.history),
    })),
    lanes: input.lanes.filter((lane): lane is ChartLane => lane !== null),
    bands: episodeBands(input.episodes, input.recessions, input.window),
    referenceLines:
      input.threshold === null
        ? []
        : [
            {
              value: input.threshold.value,
              label: input.threshold.label,
              tone: 'warning',
              dash: true,
            },
          ],
  };
}
