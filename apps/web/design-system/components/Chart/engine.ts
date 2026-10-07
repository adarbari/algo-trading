/**
 * The chart engine: the ONLY module that touches lightweight-charts (TradingView, Apache-2.0;
 * the lint boundary allows the import only under components/Chart). Draws prepared series as
 * lines or an area, event markers (shape + letter per kind), a dashed 100 line when rebased,
 * shaded bands behind the lines (bands.ts, a series primitive; solid or hatched), horizontal
 * reference lines with an end label, an optional volume pane and lanes (a thin pane each, drawn
 * by lanes.ts on the chart's own time scale), in the
 * colours and font read from the tokens; reports the crosshair position. A theme or data change redraws from scratch (cheap at daily resolution) instead of
 * patching options. Scrolling and zooming are off: the caller's range control sets the window.
 */
import {
  AreaSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type AutoscaleInfo,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';

import type { Series } from '../../tokens';
import { bandsPrimitive, type BandColours } from './bands';
import { valueBandsPrimitive } from './valueBands';
import { lanePrimitive, LANE_HEIGHT, type LaneColours } from './lanes';
import {
  EVENT_KINDS,
  snapToData,
  type ChartBand,
  type ChartBandTone,
  type ChartEvent,
  type ChartEventKind,
  type ChartLane,
  type ChartPoint,
  type ChartReferenceLine,
  type ChartValueBand,
  type PreparedSeries,
} from './chartData';

/** Colours and font for the canvas, read from the CSS tokens of the active theme. */
export interface EngineTheme {
  surface: string;
  text: string;
  text2: string;
  muted: string;
  borderSoft: string;
  control: string;
  row: string;
  accentSoft: string;
  track: string;
  fontFamily: string;
  fontSize: number;
  /** Flat tints of the shaded bands, by tone. */
  bands: BandColours;
  /** Solid colours by tone: the reference lines and the hatch lines of hatched bands. */
  tones: Record<ChartBandTone, string>;
  /** Border colours by tone: the outline of a lane segment. */
  borders: BandColours;
  series: Record<Series, string>;
}

export interface EngineInput {
  type: 'line' | 'area';
  series: readonly PreparedSeries[];
  events: readonly ChartEvent[];
  /** Shaded spans behind the series, in the price pane. */
  bands: readonly ChartBand[];
  /** Thin panes under the price pane, one per lane, on the chart's time scale. */
  lanes: readonly ChartLane[];
  /** Horizontal lines across the price pane, with an end label. */
  referenceLines: readonly ChartReferenceLine[];
  /** Shaded spans of values across the price pane. */
  valueBands: readonly ChartValueBand[];
  volume: readonly ChartPoint[];
  /** Draw the dashed reference line at 100. */
  rebase: boolean;
  /** Axis labels (the shared value formatter). */
  formatValue: (value: number) => string;
  /** Volume pane labels (a compact count, never the price's currency). */
  formatVolume: (value: number) => string;
}

export interface CrosshairInfo {
  /** ISO day under the crosshair. */
  time: string;
  /** Pixels from the plot's top-left corner. */
  x: number;
  y: number;
}

const MARKER: Record<
  ChartEventKind,
  { shape: SeriesMarker<Time>['shape']; position: 'aboveBar' | 'belowBar' }
> = {
  dividend: { shape: 'circle', position: 'aboveBar' },
  split: { shape: 'square', position: 'aboveBar' },
  earnings: { shape: 'arrowUp', position: 'belowBar' },
  filing: { shape: 'arrowDown', position: 'aboveBar' },
  macro: { shape: 'circle', position: 'belowBar' },
};

/** A point as chart data. */
function toData(p: ChartPoint): { time: string; value: number } | { time: string } {
  return p.value === null ? { time: p.time } : { time: p.time, value: p.value };
}

/** The points split at gaps (null values): one list of valued points per run between them. */
function runs(points: readonly ChartPoint[]): { time: string; value: number }[][] {
  const out: { time: string; value: number }[][] = [];
  let current: { time: string; value: number }[] = [];
  for (const p of points) {
    if (p.value === null) {
      if (current.length > 0) out.push(current);
      current = [];
    } else {
      current.push({ time: p.time, value: p.value });
    }
  }
  if (current.length > 0) out.push(current);
  return out;
}

/** lightweight-charts hands back the day as a string, a business-day object or a timestamp. */
function isoDay(time: Time): string {
  if (typeof time === 'string') return time;
  if (typeof time === 'number') return new Date(time * 1000).toISOString().slice(0, 10);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${String(time.year)}-${pad(time.month)}-${pad(time.day)}`;
}

/**
 * Draws the chart into `container` (sized by its CSS; resizes with it through ResizeObserver).
 * Returns the cleanup that removes it.
 */
export function drawChart(
  container: HTMLElement,
  input: EngineInput,
  theme: EngineTheme,
  onCrosshair: (info: CrosshairInfo | null) => void,
): () => void {
  const chart: IChartApi = createChart(container, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: theme.surface },
      textColor: theme.muted,
      fontFamily: theme.fontFamily,
      fontSize: theme.fontSize,
      attributionLogo: true,
      panes: { separatorColor: theme.borderSoft, enableResize: false },
    },
    grid: { vertLines: { visible: false }, horzLines: { color: theme.borderSoft } },
    rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.12 } },
    timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
    crosshair: {
      mode: CrosshairMode.Magnet,
      vertLine: { color: theme.control, style: LineStyle.Solid, labelBackgroundColor: theme.row },
      horzLine: { color: theme.control, style: LineStyle.Dashed, labelBackgroundColor: theme.row },
    },
    handleScroll: false,
    handleScale: false,
    kineticScroll: { mouse: false, touch: false },
  });

  // Every line and every finite band edge stays inside the price range (they do not scale it).
  const lineYs = [
    ...input.referenceLines.map((l) => l.value),
    ...input.valueBands.flatMap((b) =>
      [b.from, b.to].filter((v): v is number => v !== undefined && Number.isFinite(v)),
    ),
  ];
  const drawn: ISeriesApi<'Line' | 'Area'>[] = [];
  const firstRuns: { line: ISeriesApi<'Line' | 'Area'>; times: Set<string> }[] = [];
  input.series.forEach((s, index) => {
    const color = theme.series[s.tone];
    const common = {
      // Per series, not chart-wide (a chart-wide formatter would also format the volume pane).
      priceFormat: { type: 'custom' as const, formatter: input.formatValue, minMove: 0.01 },
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 3,
      crosshairMarkerBorderColor: theme.surface,
      crosshairMarkerBackgroundColor: color,
      // Keep every reference line inside the price range (price lines do not scale it).
      ...(drawn.length === 0 && lineYs.length > 0
        ? {
            autoscaleInfoProvider: (original: () => AutoscaleInfo | null) => {
              const base = original();
              if (!base?.priceRange) return base;
              return {
                ...base,
                priceRange: {
                  minValue: Math.min(base.priceRange.minValue, ...lineYs),
                  maxValue: Math.max(base.priceRange.maxValue, ...lineYs),
                },
              };
            },
          }
        : {}),
    };
    // The library joins a line across missing days, so each run between gaps is its own series.
    for (const run of runs(s.points)) {
      const line =
        input.type === 'area' && input.series.length === 1
          ? chart.addSeries(AreaSeries, {
              ...common,
              lineColor: color,
              lineWidth: 2,
              // A flat tint, never a gradient (design rule): the accent tint for s1, else the track.
              topColor: s.tone === 's1' ? theme.accentSoft : theme.track,
              bottomColor: s.tone === 's1' ? theme.accentSoft : theme.track,
            })
          : chart.addSeries(LineSeries, { ...common, color, lineWidth: 2 });
      line.setData(run);
      drawn.push(line);
      if (index === 0) firstRuns.push({ line, times: new Set(run.map((p) => p.time)) });
    }
  });

  if (input.series.some((s) => s.points.some((p) => p.value === null))) {
    // The time axis counts only days some series has a value for: an empty series over every day
    // keeps a gap its true width.
    const days = [...new Set(input.series.flatMap((s) => s.points.map((p) => p.time)))].sort();
    chart
      .addSeries(LineSeries, { lastValueVisible: false, priceLineVisible: false })
      .setData(days.map((time) => ({ time })));
  }

  const first = drawn[0];
  const firstPoints = input.series[0]?.points ?? [];
  if (first && input.rebase) {
    first.createPriceLine({
      price: 100,
      color: theme.control,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
    });
  }
  for (const line of first ? input.referenceLines : []) {
    first?.createPriceLine({
      price: line.value,
      color: theme.tones[line.tone ?? 'neutral'],
      lineWidth: 1,
      lineStyle: line.dash === true ? LineStyle.Dashed : LineStyle.Solid,
      axisLabelVisible: line.label !== undefined,
      title: line.label ?? '',
    });
  }
  if (first && input.valueBands.length > 0) {
    first.attachPrimitive(valueBandsPrimitive(input.valueBands, theme.bands));
  }
  if (first && input.bands.length > 0) {
    first.attachPrimitive(bandsPrimitive(input.bands, firstPoints, theme.bands, theme.tones));
  }
  if (first && input.events.length > 0) {
    const placed = input.events
      .map((event) => ({ event, time: snapToData(event.time, firstPoints) }))
      .filter((m): m is { event: ChartEvent; time: string } => m.time !== undefined)
      .sort((a, b) => (a.time < b.time ? -1 : 1));
    // A marker sits on the run of the first series that has a value that day.
    for (const { line, times } of firstRuns) {
      const markers = placed
        .filter((m) => times.has(m.time))
        .map(({ event, time }): SeriesMarker<Time> => ({
          time,
          ...MARKER[event.kind],
          color: theme.text2,
          text: EVENT_KINDS[event.kind].letter,
          size: 1,
        }));
      if (markers.length > 0) createSeriesMarkers(line, markers);
    }
  }

  if (input.volume.length > 0) {
    const volume = chart.addSeries(
      HistogramSeries,
      {
        color: theme.control,
        priceFormat: { type: 'custom', formatter: input.formatVolume, minMove: 1 },
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1,
    );
    volume.setData(input.volume.map(toData));
    const [pricePane, volumePane] = chart.panes();
    pricePane?.setStretchFactor(3);
    volumePane?.setStretchFactor(1);
  }

  if (input.lanes.length > 0) {
    const laneColours: LaneColours = {
      tints: theme.bands,
      borders: theme.borders,
      text: theme.muted,
      fontFamily: theme.fontFamily,
      fontSize: theme.fontSize,
    };
    const firstLane = chart.panes().length;
    input.lanes.forEach((lane, index) => {
      // A pane needs a series: one with no values (nothing to draw, an empty price axis) that only
      // carries the primitive.
      const carrier = chart.addSeries(
        LineSeries,
        {
          lastValueVisible: false,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
        },
        firstLane + index,
      );
      carrier.setData(firstPoints.map((p) => ({ time: p.time })));
      carrier.attachPrimitive(lanePrimitive(lane, firstPoints, laneColours));
    });
    // The library's attribution logo sits at the bottom left of the last pane: an empty pane of
    // its own keeps it off the lanes' names and strips.
    chart
      .addSeries(
        LineSeries,
        { lastValueVisible: false, priceLineVisible: false },
        firstLane + input.lanes.length,
      )
      .setData(firstPoints.map((p) => ({ time: p.time })));
    chart
      .panes()
      .slice(firstLane)
      .forEach((pane) => {
        pane.setHeight(LANE_HEIGHT);
      });
  }

  chart.timeScale().fitContent();
  chart.subscribeCrosshairMove((param) => {
    if (!param.point || param.time === undefined) {
      onCrosshair(null);
      return;
    }
    onCrosshair({ time: isoDay(param.time), x: param.point.x, y: param.point.y });
  });

  return () => {
    chart.remove();
  };
}
