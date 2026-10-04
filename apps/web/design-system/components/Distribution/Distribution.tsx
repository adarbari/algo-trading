/**
 * Distribution: a histogram of one feature across the universe (the feature catalogue: how IV30
 * or ADV is spread), with optional quantile markers (p10, median, p90) and a highlighted value
 * (the focused ticker, labelled under the axis). Bins are drawn as bars on a value axis (unequal widths allowed); marker
 * lines carry their label as text, so colour is never the only key. Plain SVG. It is an image
 * with a generated summary (count, range, the tallest bin, the markers). Loading, empty and
 * error states use Skeleton, EmptyState and ErrorState.
 */
import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import { EmptyState } from '../EmptyState';
import { ErrorState } from '../ErrorState';
import { Skeleton } from '../Skeleton';
import styles from './Distribution.module.css';
import { layoutLabels } from './labelLayout';

export interface DistributionBin {
  /** Lower edge (inclusive). */
  start: number;
  /** Upper edge (exclusive, inclusive for the last bin). */
  end: number;
  count: number;
}

export interface DistributionMarker {
  value: number;
  /** Shown above the line ("median", "p90", "AAPL"). */
  label: string;
  /** `default` (a dashed quantile line) or `accent` (the highlighted value, solid). */
  tone?: 'default' | 'accent';
}

export interface DistributionProps {
  bins: readonly DistributionBin[];
  /** What is distributed ("IV30 across 1,840 tickers"): starts the accessible summary. */
  label: string;
  /** How bin edges and markers read (default a number). */
  format?: ValueFormat;
  /**
   * Quantile lines and highlighted values. Quantile labels that would overlap are stacked or
   * dropped (earlier markers win, so list the important ones first); lines and the accessible
   * summary always keep every marker, and an accent marker's label is always shown.
   */
  markers?: readonly DistributionMarker[];
  /** Plot height: `sm` 80 px or `md` 120 px (default). */
  height?: 'sm' | 'md';
  /** `ready` (default), `loading` or `error`. */
  status?: 'ready' | 'loading' | 'error';
  errorMessage?: ReactNode;
  onRetry?: () => void;
  /** Shown when there are no values. */
  emptyMessage?: ReactNode;
}

const SCALE = 1000;
/** Width assumed before the plot is measured (and where there is no layout, as in tests). */
const FALLBACK_WIDTH = 480;
const GAP = 0.08;

/** The accessible summary of a histogram. */
export function describeDistribution(
  label: string,
  bins: readonly DistributionBin[],
  markers: readonly DistributionMarker[],
  format: ValueFormat,
): string {
  const fmt = (v: number) => formatValue(v, format).text;
  const total = bins.reduce((sum, bin) => sum + bin.count, 0);
  const tallest = bins.reduce(
    (top, bin) => (bin.count > top.count ? bin : top),
    bins[0] as DistributionBin,
  );
  const first = bins[0] as DistributionBin;
  const last = bins.at(-1) as DistributionBin;
  const parts = [
    `${label}: ${formatValue(total, { kind: 'number' }).text} values from ${fmt(first.start)} to ${fmt(last.end)}`,
    `most in ${fmt(tallest.start)} to ${fmt(tallest.end)} (${formatValue(tallest.count, { kind: 'number' }).text})`,
  ];
  if (markers.length > 0) parts.push(markers.map((m) => `${m.label} ${fmt(m.value)}`).join(', '));
  return `${parts.join('; ')}.`;
}

const edgeOf = (fraction: number) =>
  fraction < 0.08 ? 'start' : fraction > 0.92 ? 'end' : undefined;

export function Distribution({
  bins,
  label,
  format = { kind: 'number' },
  markers = [],
  height = 'md',
  status = 'ready',
  errorMessage = 'The distribution could not load.',
  onRetry,
  emptyMessage = 'No values to show.',
}: DistributionProps) {
  const plotRef = useRef<HTMLDivElement>(null);
  const [plotWidth, setPlotWidth] = useState(FALLBACK_WIDTH);
  useLayoutEffect(() => {
    const el = plotRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const measure = () => {
      if (el.clientWidth > 0) setPlotWidth(el.clientWidth);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  });
  if (status === 'loading')
    return <Skeleton variant="rect" height="sm" label={`Loading ${label}`} />;
  if (status === 'error') {
    return (
      <ErrorState compact title={errorMessage} {...(onRetry === undefined ? {} : { onRetry })} />
    );
  }
  const total = bins.reduce((sum, bin) => sum + bin.count, 0);
  if (bins.length === 0 || total === 0) return <EmptyState compact title={emptyMessage} />;

  const min = Math.min(...bins.map((b) => b.start), ...markers.map((m) => m.value));
  const max = Math.max(...bins.map((b) => b.end), ...markers.map((m) => m.value));
  const span = max - min || 1;
  const x = (v: number) => ((v - min) / span) * SCALE;
  const tallest = Math.max(...bins.map((b) => b.count));
  const fmt = (v: number) => formatValue(v, format).text;
  const at = (v: number) => ({
    style: { insetInlineStart: `${((x(v) / SCALE) * 100).toFixed(2)}%` } as CSSProperties,
  });
  // Quantile labels share two rows above the plot; the accent label sits under the axis.
  const quantiles = markers.filter((m) => m.tone !== 'accent');
  const placed = layoutLabels(
    quantiles.map((m) => ({
      x: (x(m.value) / SCALE) * plotWidth,
      chars: `${m.label} ${fmt(m.value)}`.length,
    })),
    plotWidth,
  );
  const placement = new Map(quantiles.map((m, i) => [m, placed[i]]));
  const rows = placed.some((p) => p.row === 1) ? 2 : 1;

  return (
    <div
      className={styles.root}
      role="img"
      aria-label={describeDistribution(label, bins, markers, format)}
    >
      <div
        className={styles.plot}
        data-height={height}
        data-markers={markers.length > 0 ? rows : undefined}
        ref={plotRef}
      >
        <svg
          className={styles.svg}
          viewBox={`0 0 ${String(SCALE)} 100`}
          preserveAspectRatio="none"
          aria-hidden="true"
          focusable="false"
        >
          {bins.map((bin) => {
            const width = x(bin.end) - x(bin.start);
            const h = (bin.count / tallest) * 100;
            return (
              <rect
                key={`${String(bin.start)}-${String(bin.end)}`}
                className={styles.bar}
                x={x(bin.start) + (width * GAP) / 2}
                width={width * (1 - GAP)}
                y={100 - h}
                height={h}
              />
            );
          })}
        </svg>
        {markers.map((marker) => {
          const { style } = at(marker.value);
          const accent = marker.tone === 'accent';
          const place = placement.get(marker);
          const hidden = !accent && place?.row === 'hidden';
          const edge = accent ? edgeOf(x(marker.value) / SCALE) : place?.edge;
          return (
            <span
              key={`${marker.label}-${String(marker.value)}`}
              className={styles.marker}
              data-tone={marker.tone ?? 'default'}
              data-edge={edge}
              data-row={place?.row === 1 ? 1 : undefined}
              style={style}
              aria-hidden="true"
            >
              {hidden ? null : (
                <span className={styles.markerLabel}>
                  {marker.label} {fmt(marker.value)}
                </span>
              )}
            </span>
          );
        })}
      </div>
      <div className={styles.axis} aria-hidden="true">
        <span>{fmt(min)}</span>
        <span>{fmt(max)}</span>
      </div>
    </div>
  );
}
