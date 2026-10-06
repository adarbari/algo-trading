/**
 * ScoreMeter: a horizontal meter for one score on a bounded scale (0-100 by default): a filled
 * track with a marker at the value, optional threshold ticks with their labels under the track
 * ("50 caution", "75 stress"), and a tone taken from the band the value sits in (the status
 * tones of StatusBadge). The band's label is written next to the value, so colour is never the
 * only signal. The axis always runs from low risk (left) to high risk (right): `direction`
 * `lower-is-risk` (a cushion, a margin) turns the scale around, so a falling value moves toward
 * the risky end and a threshold's band runs below it; a value off the scale pins the marker to
 * the nearer end and the reading says "above range" or "below range". Exposed as a meter (`role="meter"`) whose text names the band; an unknown score
 * draws a dashed empty track with the reason as text (an image named "<label>: unknown").
 */
import { useId, type CSSProperties, type ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { type DataTone, toneStyles } from '../Legend';
import { Skeleton } from '../Skeleton';
import styles from './ScoreMeter.module.css';

/** Which end of the scale is risky: the high values (default) or the low ones. */
export type ScoreDirection = 'higher-is-risk' | 'lower-is-risk';

export interface ScoreThreshold {
  /** Where the band starts, on the same scale as `value` (the band runs on toward risk, to the next threshold). */
  at: number;
  /** The band's name ("caution"): shown under the track and beside the value while inside it. */
  label: string;
  /** Tone of the fill and marker while the value is inside this band. */
  tone: DataTone;
}

export interface ScoreMeterProps {
  /** The score. `null` / `undefined` = unknown: a dashed empty track and `unknownReason`. */
  value: number | null | undefined;
  /** Scale start (default 0). */
  min?: number;
  /** Scale end (default 100). */
  max?: number;
  /** Band starts, in any order: the value takes the tone of the last threshold it has reached (at it counts as reached). */
  thresholds?: readonly ScoreThreshold[];
  /** Tone on the low-risk side of the first threshold, and for a meter without thresholds (default `accent`). */
  baseTone?: DataTone;
  /** Name of the band on the low-risk side of the first threshold ("calm"); without it that band has no text. */
  baseLabel?: string;
  /** Name of the score ("Slow-warning score"): shown above the track, names the meter. */
  label: string;
  /** A line under the meter: what the score means, or when it changed. */
  caption?: ReactNode;
  /** Why there is no score ("No macro data for 2 Oct"). Shown instead of the value. */
  unknownReason?: string;
  /** How the value reads (default a whole number). */
  format?: ValueFormat;
  /** The unit after the value and the thresholds ("%", "bp", "pts"). */
  unit?: string;
  /** `higher-is-risk` (default) or `lower-is-risk`: which end of `min`-`max` is the risky one. */
  direction?: ScoreDirection;
  /** Track thickness: `sm` 6 px (lists, default) or `md` 10 px (a headline meter). */
  size?: 'sm' | 'md';
  /** Placeholder while the score loads. */
  loading?: boolean;
}

/** Position along the axis (low risk 0, high risk 1; clamped): the scale turned for lower-is-risk. */
function fraction(value: number, min: number, max: number, lower: boolean): number {
  const f = max > min ? Math.min(1, Math.max(0, (value - min) / (max - min))) : 0;
  return lower ? 1 - f : f;
}

/** The band a value has reached: the last threshold, in risk order, it is at or past. */
function bandOf(
  value: number,
  thresholds: readonly ScoreThreshold[],
  lower: boolean,
): ScoreThreshold | undefined {
  return thresholds.filter((t) => (lower ? value <= t.at : value >= t.at)).at(-1);
}

export function ScoreMeter({
  value,
  min = 0,
  max = 100,
  thresholds = [],
  baseTone = 'accent',
  baseLabel,
  label,
  caption,
  unknownReason = 'Not available',
  format = { kind: 'number' },
  unit,
  direction = 'higher-is-risk',
  size = 'sm',
  loading = false,
}: ScoreMeterProps) {
  const captionId = useId();
  const keyId = useId();
  if (loading) return <Skeleton lines={2} label={`Loading ${label}`} />;

  const lower = direction === 'lower-is-risk';
  // In risk order: ascending for higher-is-risk, descending for lower-is-risk.
  const sorted = [...thresholds]
    .filter((t) => t.at > min && t.at < max)
    .sort((a, b) => (lower ? b.at - a.at : a.at - b.at));
  const known = typeof value === 'number' && !Number.isNaN(value);
  const show = (n: number) =>
    `${formatValue(n, format).text}${unit === undefined ? '' : ` ${unit}`}`;
  const text = known ? show(value) : '';
  const range =
    known && value > max ? 'above range' : known && value < min ? 'below range' : undefined;
  const reached = known ? bandOf(value, sorted, lower) : undefined;
  const band = reached ?? (known && baseLabel !== undefined ? { label: baseLabel } : undefined);
  const tone = reached?.tone ?? baseTone;
  const position = known ? fraction(value, min, max, lower) : 0;
  const describedBy = [caption === undefined ? null : captionId, sorted.length > 0 ? keyId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={styles.root}>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        {known ? (
          <span className={styles.reading} aria-hidden="true">
            <span className={styles.value}>{text}</span>
            {band && <span className={styles.band}>{band.label}</span>}
            {range && <span className={styles.band}>{range}</span>}
          </span>
        ) : (
          <span className={styles.reason}>{unknownReason}</span>
        )}
      </div>
      <div
        className={`${styles.track} ${toneStyles.tone}`}
        data-size={size}
        data-tone={tone}
        data-unknown={!known || undefined}
        data-offscale={range !== undefined || undefined}
        style={{ '--pos': `${String(position * 100)}%` } as CSSProperties}
        {...(known
          ? {
              role: 'meter',
              'aria-label': label,
              'aria-valuemin': min,
              'aria-valuemax': max,
              'aria-valuenow': Math.min(max, Math.max(min, value)),
              'aria-valuetext': [text, band?.label, range].filter(Boolean).join(', '),
              ...(describedBy ? { 'aria-describedby': describedBy } : {}),
            }
          : { role: 'img', 'aria-label': `${label}: unknown. ${unknownReason}` })}
      >
        {known && <span className={styles.fill} />}
        {sorted.map((t) => (
          <span
            key={t.at}
            className={styles.cut}
            aria-hidden="true"
            style={{ '--at': `${String(fraction(t.at, min, max, lower) * 100)}%` } as CSSProperties}
          />
        ))}
        {known && <span className={styles.marker} aria-hidden="true" />}
      </div>
      {sorted.length > 0 && (
        <>
          <div className={styles.ticks} aria-hidden="true">
            {sorted.map((t) => {
              const at = fraction(t.at, min, max, lower);
              return (
                <span
                  key={t.at}
                  className={styles.tick}
                  data-align={at < 0.12 ? 'start' : at > 0.88 ? 'end' : 'center'}
                  style={{ '--at': `${String(at * 100)}%` } as CSSProperties}
                >
                  {show(t.at)} {t.label}
                </span>
              );
            })}
          </div>
          <VisuallyHidden id={keyId}>
            {`Bands: ${sorted.map((t) => `${t.label} ${lower ? 'at or below' : 'from'} ${show(t.at)}`).join(', ')}.`}
          </VisuallyHidden>
        </>
      )}
      {caption !== undefined && (
        <span id={captionId} className={styles.caption}>
          {caption}
        </span>
      )}
    </div>
  );
}
