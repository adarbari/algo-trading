/**
 * The evidence curve laid out for the chart: the picks and the universe base as lines, the paper
 * record continuing the picks as a dashed stroke from its server-given anchor, the in-sample and
 * out-of-sample stretches as bands (each point carries the harness's own period mark), the
 * spans that hold no number as one lane, and the format the unit calls for. Nothing here
 * computes a figure: every value, date and mark is the server's; this only arranges them.
 */
import type { ChartBand, ChartLane, ChartPoint, ChartSeries, ValueFormat } from '@algotrade/ui';

import type { CurveGap, EdgeCurve } from '@/entities/edge';
import { periodLabel } from '@/entities/edge';

const GAP_LABELS: Record<string, string> = {
  excluded_coverage: 'Excluded: coverage',
  lost_input: 'Lost input',
  no_picks: 'No picks',
};

export const gapLabel = (gap: CurveGap): string => GAP_LABELS[gap.kind] ?? gap.kind;

/** One value per day, the last wins (a chart takes a day once). */
function oneADay(points: readonly ChartPoint[]): ChartPoint[] {
  const byDay = new Map<string, ChartPoint>();
  for (const point of points) byDay.set(point.time, point);
  return [...byDay.values()].sort((a, b) => a.time.localeCompare(b.time));
}

export interface CurveChart {
  series: ChartSeries[];
  bands: ChartBand[];
  lanes: ChartLane[];
  format: ValueFormat;
}

/** A return is a fraction (shown as a signed percent); excess wins are a count of wins. */
export const curveFormat = (curve: EdgeCurve): ValueFormat =>
  curve.kind === 'excess_wins'
    ? { kind: 'delta', unit: 'number', digits: 1 }
    : { kind: 'delta', unit: 'percent', digits: 1 };

function bands(curve: EdgeCurve): ChartBand[] {
  const spans = new Map<string, { start: string; end: string }>();
  for (const point of curve.points) {
    const span = spans.get(point.period);
    if (span) span.end = point.exit;
    else spans.set(point.period, { start: point.exit, end: point.exit });
  }
  // A run with no split (`all`) has two sides to mark no more.
  if (spans.size === 1 && spans.has('all')) return [];
  return [...spans.entries()].map(([period, span]) => ({
    ...span,
    tone: period === 'out_of_sample' ? 'info' : 'neutral',
    label: periodLabel(period),
  }));
}

/** The decoys the curve can draw, by name (a decoy is a toggle on the page, off at first). */
export const decoyNames = (curve: EdgeCurve): string[] => curve.baselines.map((b) => b.baseline);

/** The curve with the decoys named in `decoys` drawn as lines beside the picks. */
export function curveChart(curve: EdgeCurve, decoys: readonly string[] = []): CurveChart {
  const series: ChartSeries[] = [
    {
      id: 'picks',
      label: 'Picks',
      points: oneADay(curve.points.map((p) => ({ time: p.exit, value: p.cumulative }))),
    },
  ];
  if (curve.points.some((p) => p.baseCumulative != null)) {
    series.push({
      id: 'base',
      label: 'Universe',
      points: oneADay(curve.points.map((p) => ({ time: p.exit, value: p.baseCumulative }))),
    });
  }
  for (const decoy of curve.baselines) {
    if (!decoys.includes(decoy.baseline)) continue;
    series.push({
      id: `decoy:${decoy.baseline}`,
      label: decoy.baseline,
      points: oneADay(decoy.points.map((p) => ({ time: p.exit, value: p.cumulative }))),
    });
  }
  const live = curve.live;
  if (live && live.points.length > 0) {
    const from: ChartPoint[] =
      live.since != null && live.anchor != null ? [{ time: live.since, value: live.anchor }] : [];
    series.push({
      id: 'live',
      label: 'Paper',
      stroke: 'dashed',
      points: oneADay([
        ...from,
        ...live.points.map((p) => ({ time: p.sell, value: p.cumulative })),
      ]),
    });
  }
  const lanes: ChartLane[] =
    curve.gaps.length === 0
      ? []
      : [
          {
            id: 'gaps',
            label: 'Not measured',
            segments: curve.gaps.map((g) => ({
              start: g.from,
              end: g.to,
              tone: 'neutral',
              label: gapLabel(g),
            })),
          },
        ];
  return { series, bands: bands(curve), lanes, format: curveFormat(curve) };
}
