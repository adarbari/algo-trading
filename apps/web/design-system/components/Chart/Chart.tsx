/**
 * Chart: THE time-series chart (price history, rebased comparisons, a feature over time), one
 * wrapper around lightweight-charts, which stays inside this folder. Lines (or one area) in the
 * series colours s1-s6, optionally rebased to 100 at the start of the window; event markers
 * (ex-dividend, split, earnings) with a shape and letter each plus a key; optional shaded bands
 * (spans of days in a status tint behind the lines: regimes, drawdowns, recessions), named in a
 * key and in a text list for assistive technology; an optional volume pane; a crosshair read-out with tabular values (formatValue). The caller owns the time window
 * (`range`, usually a SegmentedControl passed as `toolbar`). Resizes with its container, redraws
 * in the active theme's tokens when the theme changes, and has no animation (scroll / zoom
 * off). Accessible: an image with a generated text summary, and a "View as table" switch that
 * shows the same numbers in a DataTable. Loading, empty and error states.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import { Button } from '../Button';
import { DataTable, type DataTableColumn } from '../DataTable';
import { EmptyState } from '../EmptyState';
import { ErrorState } from '../ErrorState';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { Skeleton } from '../Skeleton';
import styles from './Chart.module.css';
import {
  describeChart,
  prepare,
  snapToData,
  tableRows,
  type ChartBand,
  type ChartEvent,
  type ChartPoint,
  type ChartRange,
  type ChartSeries,
  type ChartTableRow,
} from './chartData';
import { ChartLegend } from './ChartLegend';
import { readTheme, useThemeVersion } from './chartTheme';
import { ChartTooltip } from './ChartTooltip';
import { drawChart, type CrosshairInfo } from './engine';

export interface ChartProps {
  /** What the chart shows ("AAPL close", "AAPL, MSFT and NVDA"): the summary's first words. */
  label: string;
  /** One or more series (up to six; colours s1-s6 in order unless a series sets `tone`). */
  series: readonly ChartSeries[];
  /** `line` (default) or `area` (a single series only; flat tint, never a gradient). */
  type?: 'line' | 'area';
  /** The time window, counted back from the latest point: 3M, 1Y, 2Y or All (default). */
  range?: ChartRange;
  /** Show each series as 100 x value / first value in the window (compare performance). */
  rebase?: boolean;
  /** Ex-dividend, split and earnings markers on the first series. */
  events?: readonly ChartEvent[];
  /**
   * Shaded spans of days behind the series, in the price pane: a start and end day, a status
   * tone and a label. Their labels are listed for screen readers and keyed under the chart.
   */
  bands?: readonly ChartBand[];
  /** Show the bands in the key (default true; the hidden list for screen readers stays). */
  bandKey?: boolean;
  /** Daily volume in a pane under the price. */
  volume?: readonly ChartPoint[];
  /** How values read on the axis, read-out and table (default currency; rebased: 1 decimal). */
  format?: ValueFormat;
  /** Plot height: `sm` 160 px, `md` 240 px (default), `lg` 320 px. */
  height?: 'sm' | 'md' | 'lg';
  /** Controls on the key's row (the caller's range SegmentedControl). */
  toolbar?: ReactNode;
  /** Offer the "View as table" switch (default true). */
  tableView?: boolean;
  /** `ready` (default), `loading` or `error`. */
  status?: 'ready' | 'loading' | 'error';
  errorMessage?: ReactNode;
  onRetry?: () => void;
  /** Shown when no series has points in the window. */
  emptyMessage?: ReactNode;
}

/** A Map of day -> value for each series (read-out lookups). */
function byDay(points: readonly ChartPoint[]): Map<string, number> {
  return new Map(points.map((p) => [p.time, p.value]));
}

const dateText = (day: string) => formatValue(day, { kind: 'date', style: 'short' }).text;

/** Volume is a count of shares: compact (800M), whatever the price format is. */
const VOLUME_FORMAT = { kind: 'compact' } as const satisfies ValueFormat;

export function Chart({
  label,
  series,
  type = 'line',
  range = 'All',
  rebase = false,
  events,
  bands,
  bandKey = true,
  volume,
  format,
  height = 'md',
  toolbar,
  tableView = true,
  status = 'ready',
  errorMessage = 'The chart could not load.',
  onRetry,
  emptyMessage = 'No data in this range.',
}: ChartProps) {
  const valueFormat: ValueFormat =
    format ?? (rebase ? { kind: 'number', digits: 1 } : { kind: 'currency' });
  const chart = useMemo(
    () =>
      prepare(series, {
        range,
        rebase,
        ...(events ? { events } : {}),
        ...(bands ? { bands } : {}),
        ...(volume ? { volume } : {}),
      }),
    [series, range, rebase, events, bands, volume],
  );
  const summary = describeChart(label, chart, { rebase, format: valueFormat });
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const [crosshair, setCrosshair] = useState<(CrosshairInfo & { width: number }) | null>(null);
  const [ready, setReady] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const themeVersion = useThemeVersion();
  const hasData = chart.series.length > 0;
  const showCanvas = status === 'ready' && hasData && view === 'chart';

  const lookups = useMemo(() => {
    const firstPoints = chart.series[0]?.points ?? [];
    const eventsByDay = new Map<string, ChartEvent[]>();
    for (const e of chart.events) {
      const day = snapToData(e.time, firstPoints);
      if (day !== undefined) eventsByDay.set(day, [...(eventsByDay.get(day) ?? []), e]);
    }
    return {
      values: new Map(chart.series.map((s) => [s.id, byDay(s.points)])),
      volume: byDay(chart.volume),
      events: eventsByDay,
    };
  }, [chart]);

  // A stable key, so a caller's inline `format` object does not redraw the chart every render.
  const formatKey = JSON.stringify(valueFormat);

  useEffect(() => {
    const element = host.current;
    if (!showCanvas || !element) return undefined;
    let cleanup: (() => void) | undefined;
    let cancelled = false;
    let frame = 0;
    setReady(false);
    const theme = readTheme(element);
    const axisFormat = JSON.parse(formatKey) as ValueFormat;
    // The canvas cannot wait for web fonts by itself: load the UI face before the first draw.
    const fonts = typeof document.fonts === 'undefined' ? undefined : document.fonts;
    // Regular for labels, bold for the axis's major ticks (years).
    const fontsReady = fonts
      ? Promise.all(
          ['400', 'bold'].map((weight) =>
            fonts.load(`${weight} ${String(theme.fontSize)}px ${theme.fontFamily}`),
          ),
        ).catch(() => [])
      : Promise.resolve([]);
    void fontsReady.then(() => {
      if (cancelled) return;
      cleanup = drawChart(
        element,
        {
          type,
          series: chart.series,
          events: chart.events,
          bands: chart.bands,
          volume: chart.volume,
          rebase,
          formatValue: (v) => formatValue(v, axisFormat).text,
          formatVolume: (v) => formatValue(v, VOLUME_FORMAT).text,
        },
        theme,
        (info) => {
          setCrosshair(info ? { ...info, width: element.clientWidth } : null);
        },
      );
      // Ready (for screenshots) once the canvas has painted: two frames after the draw.
      frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(() => {
          setReady(true);
        });
      });
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      cleanup?.();
      setCrosshair(null);
    };
  }, [showCanvas, chart, type, rebase, themeVersion, formatKey]);

  if (status === 'loading') {
    const skeletonHeight = height === 'lg' ? 'lg' : height === 'sm' ? 'sm' : 'md';
    return <Skeleton variant="rect" height={skeletonHeight} label={`Loading ${label}`} />;
  }
  if (status === 'error') {
    return <ErrorState title={errorMessage} {...(onRetry === undefined ? {} : { onRetry })} />;
  }
  if (!hasData) return <EmptyState compact title={emptyMessage} />;

  const columns: DataTableColumn<ChartTableRow>[] = [
    {
      id: 'time',
      header: 'Date',
      value: (r) => r.time,
      format: { kind: 'date', style: 'short' },
      width: 'md',
      hideable: false,
    },
    ...chart.series.map((s): DataTableColumn<ChartTableRow> => ({
      id: `series-${s.id}`,
      header: s.label,
      value: (r) => r.values[s.id],
      format: valueFormat,
    })),
    ...(chart.volume.length > 0
      ? [
          {
            id: 'volume',
            header: 'Volume',
            value: (r: ChartTableRow) => r.volume,
            format: VOLUME_FORMAT,
          },
        ]
      : []),
    ...(chart.bands.length > 0
      ? [
          {
            id: 'shaded',
            header: 'Shaded',
            value: (r: ChartTableRow) => r.shaded,
            width: 'md' as const,
          },
        ]
      : []),
    ...(chart.events.length > 0
      ? [
          {
            id: 'events',
            header: 'Events',
            value: (r: ChartTableRow) => r.events,
            width: 'lg' as const,
            grow: true,
          },
        ]
      : []),
  ];

  return (
    <div className={styles.root}>
      <div className={styles.bar}>
        <ChartLegend chart={chart} bandKey={bandKey} />
        <div className={styles.tools}>
          {toolbar}
          {tableView && (
            <Button
              size="sm"
              variant="ghost"
              {...(view === 'chart' ? { icon: 'columns' as const } : {})}
              onClick={() => {
                setView(view === 'chart' ? 'table' : 'chart');
              }}
            >
              {view === 'chart' ? 'View as table' : 'View as chart'}
            </Button>
          )}
        </div>
      </div>
      {view === 'chart' && chart.bands.length > 0 && (
        <VisuallyHidden as="div">
          <ul aria-label={`${label}: shaded periods`}>
            {chart.bands.map((b) => (
              <li key={`${b.start}-${b.label}`}>
                {`${b.label}: ${dateText(b.start)} to ${dateText(b.end)}`}
              </li>
            ))}
          </ul>
        </VisuallyHidden>
      )}
      {view === 'chart' ? (
        <div className={styles.plot} data-height={height} data-ready={ready || undefined}>
          {/* The text alternative: an image over the canvas (the canvas host holds the library's
              attribution link, which must not sit inside role="img"). */}
          <div className={styles.summary} role="img" aria-label={summary} />
          <div ref={host} className={styles.canvas} />
          {crosshair && (
            <ChartTooltip
              at={crosshair}
              chart={chart}
              values={lookups.values}
              volume={lookups.volume}
              events={lookups.events}
              format={valueFormat}
              width={crosshair.width}
            />
          )}
        </div>
      ) : (
        <DataTable
          label={`${label}: data`}
          columns={columns}
          rows={tableRows(chart)}
          getRowId={(r) => r.time}
          visibleRows={8}
          rowLines={1}
        />
      )}
    </div>
  );
}
