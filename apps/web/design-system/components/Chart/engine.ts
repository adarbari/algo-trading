/**
 * The chart engine: the ONLY module that touches lightweight-charts (TradingView, Apache-2.0;
 * the lint boundary allows the import only under components/Chart). Draws prepared series as
 * lines or an area, event markers (shape + letter per kind), a dashed 100 line when rebased and
 * an optional volume pane, in the colours and font read from the tokens; reports the crosshair
 * position. A theme or data change redraws from scratch (cheap at daily resolution) instead of
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
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';

import type { Series } from '../../tokens';
import {
  EVENT_KINDS,
  snapToData,
  type ChartEvent,
  type ChartEventKind,
  type ChartPoint,
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
  series: Record<Series, string>;
}

export interface EngineInput {
  type: 'line' | 'area';
  series: readonly PreparedSeries[];
  events: readonly ChartEvent[];
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
};

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

  const drawn: ISeriesApi<'Line' | 'Area'>[] = input.series.map((s) => {
    const color = theme.series[s.tone];
    const common = {
      // Per series, not chart-wide (a chart-wide formatter would also format the volume pane).
      priceFormat: { type: 'custom' as const, formatter: input.formatValue, minMove: 0.01 },
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 3,
      crosshairMarkerBorderColor: theme.surface,
      crosshairMarkerBackgroundColor: color,
    };
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
    line.setData(s.points.map((p) => ({ time: p.time, value: p.value })));
    return line;
  });

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
  if (first && input.events.length > 0) {
    const markers = input.events
      .map((event) => ({ event, time: snapToData(event.time, firstPoints) }))
      .filter((m): m is { event: ChartEvent; time: string } => m.time !== undefined)
      .sort((a, b) => (a.time < b.time ? -1 : 1))
      .map(({ event, time }): SeriesMarker<Time> => ({
        time,
        ...MARKER[event.kind],
        color: theme.text2,
        text: EVENT_KINDS[event.kind].letter,
        size: 1,
      }));
    createSeriesMarkers(first, markers);
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
    volume.setData(input.volume.map((p) => ({ time: p.time, value: p.value })));
    const [pricePane, volumePane] = chart.panes();
    pricePane?.setStretchFactor(3);
    volumePane?.setStretchFactor(1);
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
