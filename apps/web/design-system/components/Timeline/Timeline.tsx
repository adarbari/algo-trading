/**
 * Timeline: rows that share one numeric axis, each with spans (a bar from one value to another,
 * open at an end while it is still going) and markers (a point on the axis). Days from an event,
 * sessions from a peak, minutes into a run: the axis is just numbers, `format` says how to write
 * them. An optional reference line marks the zero point (the peak). Pure CSS, no chart library.
 * Colour is never the only key: every mark has a text label for screen readers and the native
 * tooltip, a row can carry a `note` (its state in words), and marker shapes differ. The axis
 * range is the rows' extent unless `domain` is given; share one `domain` (see `timelineDomain`)
 * to line up several timelines.
 */
import type { CSSProperties, ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { type DataTone, toneStyles } from '../Legend';
import { Skeleton } from '../Skeleton';
import styles from './Timeline.module.css';

export interface TimelineSpan {
  id: string;
  /** Where the bar starts, on the axis. */
  from: number;
  /** Where it ends; null: still going at the end of the axis. */
  to: number | null;
  tone: DataTone;
  /** `outline` draws the bar hollow (a weaker or late reading). */
  variant?: 'solid' | 'outline';
  /** The start is not known (the bar may have begun earlier). */
  openStart?: boolean;
  /** What the bar is, for the tooltip and screen readers ("Credit spreads"). */
  label: string;
}

export interface TimelineMarker {
  id: string;
  /** Where the point sits, on the axis. */
  at: number;
  tone: DataTone;
  /** `dot` (default) or `diamond`, so two kinds differ by more than colour. */
  shape?: 'dot' | 'diamond';
  /** Draw the point hollow. */
  hollow?: boolean;
  /** What the point is ("Yield curve flagged"), for the tooltip and screen readers. */
  label: string;
}

export interface TimelineRow {
  id: string;
  /** The row's name, left of its marks (above them on a phone). */
  label: string;
  /** A short state in words beside the label ("Late", "Never fired"). */
  note?: ReactNode;
  spans?: readonly TimelineSpan[];
  markers?: readonly TimelineMarker[];
}

export interface TimelineDomain {
  min: number;
  max: number;
}

export interface TimelineProps {
  rows: readonly TimelineRow[];
  /** What the timeline shows, naming the list ("When each warning sign flagged"). */
  label: string;
  /** The axis range (default: the extent of the rows and the reference). */
  domain?: TimelineDomain;
  /** A line through every row (the peak, "0"), labelled under the axis. */
  reference?: { at: number; label: string };
  /** What the axis counts ("Sessions from the peak"). */
  axisLabel?: string;
  /** How axis values and mark positions are written (default grouped number). */
  format?: ValueFormat;
  /** Row height: `md` (default) or `sm` for an overview of many rows. */
  size?: 'sm' | 'md';
  /** Placeholder rows while loading. */
  loading?: boolean;
  /** Replaces the rows with this message. */
  error?: ReactNode;
  /** Shown when there are no rows. */
  emptyMessage?: ReactNode;
}

const STEPS = [1, 2, 5];
const MAX_TICKS = 6;

/** The smallest 1, 2 or 5 times a power of ten that puts at most six ticks on `range`. */
function niceStep(range: number): number {
  const base = 10 ** Math.floor(Math.log10(Math.max(range, 1) / MAX_TICKS));
  for (const power of [base, base * 10]) {
    for (const step of STEPS) {
      if (range / (step * power) <= MAX_TICKS) return step * power;
    }
  }
  return base * 10;
}

/**
 * One axis range for several timelines: the extent of every row's marks and spans (and the
 * reference), rounded outward to the tick step. Open ends are not counted.
 */
export function timelineDomain(
  rowSets: readonly (readonly TimelineRow[])[],
  reference?: number,
): TimelineDomain {
  const values: number[] = reference === undefined ? [] : [reference];
  for (const rows of rowSets) {
    for (const row of rows) {
      for (const span of row.spans ?? []) {
        values.push(span.from);
        if (span.to !== null) values.push(span.to);
      }
      for (const marker of row.markers ?? []) values.push(marker.at);
    }
  }
  if (values.length === 0) return { min: -10, max: 10 };
  const low = Math.min(...values);
  const high = Math.max(...values);
  if (low === high) return { min: low - 1, max: high + 1 };
  const step = niceStep(high - low);
  return { min: Math.floor(low / step) * step, max: Math.ceil(high / step) * step };
}

function ticksOf(domain: TimelineDomain): number[] {
  const step = niceStep(domain.max - domain.min);
  const first = Math.ceil(domain.min / step) * step;
  const ticks: number[] = [];
  for (let at = first; at <= domain.max; at += step) ticks.push(at);
  return ticks;
}

const clamp = (value: number) => Math.min(1, Math.max(0, value));

function describe(row: TimelineRow, format: ValueFormat): string {
  const parts = [
    ...(row.spans ?? []).map((span) => {
      const from = formatValue(span.from, format).text;
      const to = span.to === null ? 'still on' : formatValue(span.to, format).text;
      return `${span.label} ${from} to ${to}`;
    }),
    ...(row.markers ?? []).map(
      (marker) => `${marker.label} ${formatValue(marker.at, format).text}`,
    ),
  ];
  return parts.join('; ');
}

export function Timeline({
  rows,
  label,
  domain: given,
  reference,
  axisLabel,
  format = { kind: 'number' },
  size = 'md',
  loading = false,
  error,
  emptyMessage = 'Nothing to show',
}: TimelineProps) {
  if (error !== undefined && error !== null && error !== false) {
    return (
      <p className={styles.message} data-tone="negative" role="alert">
        {error}
      </p>
    );
  }
  if (loading) return <Skeleton variant="table" rows={4} columns={2} label={`${label}: loading`} />;
  if (rows.length === 0) return <p className={styles.message}>{emptyMessage}</p>;

  const domain = given ?? timelineDomain([rows], reference?.at);
  const width = domain.max - domain.min;
  const place = (value: number) => (width > 0 ? clamp((value - domain.min) / width) : 0);
  const ticks = ticksOf(domain);
  const referenceAt = reference === undefined ? undefined : place(reference.at);
  const at = (fraction: number): CSSProperties => ({ '--at': String(fraction) }) as CSSProperties;

  return (
    <div className={styles.root} data-size={size}>
      <ul className={styles.rows} aria-label={label}>
        {rows.map((row) => (
          <li key={row.id} className={styles.row}>
            <div className={styles.name}>
              <span className={styles.label}>{row.label}</span>
              {row.note !== undefined && <span className={styles.note}>{row.note}</span>}
            </div>
            <div className={styles.plot}>
              {ticks.map((tick) => (
                <span
                  key={tick}
                  className={styles.grid}
                  style={at(place(tick))}
                  aria-hidden="true"
                />
              ))}
              {referenceAt !== undefined && (
                <span className={styles.reference} style={at(referenceAt)} aria-hidden="true" />
              )}
              {(row.spans ?? []).map((span) => {
                const from = place(span.from);
                const to = span.to === null ? 1 : place(span.to);
                return (
                  <span
                    key={span.id}
                    className={`${styles.span} ${toneStyles.tone}`}
                    data-tone={span.tone}
                    data-variant={span.variant ?? 'solid'}
                    data-open-start={span.openStart === true ? '' : undefined}
                    data-open-end={span.to === null ? '' : undefined}
                    style={
                      {
                        '--from': String(from),
                        '--len': String(Math.max(0, to - from)),
                      } as CSSProperties
                    }
                    title={span.label}
                    aria-hidden="true"
                  />
                );
              })}
              {(row.markers ?? []).map((marker) => (
                <span
                  key={marker.id}
                  className={`${styles.marker} ${toneStyles.tone}`}
                  data-tone={marker.tone}
                  data-shape={marker.shape ?? 'dot'}
                  data-hollow={marker.hollow === true ? '' : undefined}
                  style={at(place(marker.at))}
                  title={marker.label}
                  aria-hidden="true"
                />
              ))}
              <VisuallyHidden>{describe(row, format)}</VisuallyHidden>
            </div>
          </li>
        ))}
      </ul>
      <div className={styles.axis} aria-hidden="true">
        <div className={styles.axisPlot}>
          {ticks.map((tick) => (
            <span key={tick} className={styles.tick} style={at(place(tick))}>
              {formatValue(tick, format).text}
            </span>
          ))}
        </div>
      </div>
      {(axisLabel !== undefined || reference !== undefined) && (
        <p className={styles.caption}>
          {axisLabel}
          {axisLabel !== undefined && reference !== undefined && ' · '}
          {reference !== undefined && `Line: ${reference.label}`}
        </p>
      )}
    </div>
  );
}
