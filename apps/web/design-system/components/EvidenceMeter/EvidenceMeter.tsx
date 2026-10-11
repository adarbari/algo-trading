/**
 * EvidenceMeter: evidence collected against evidence needed ("5 of 40 trades"): a track filled
 * from the left to `value` of `max` (clamped), milestone ticks on the track with their labels
 * under it (a tick at or below the value is drawn as reached), and an optional one-line caption
 * (the page passes the projected date). A milestone's reached state is also in its text for
 * screen readers. Exposed as a meter (`role="meter"`) with a "5 of 40" reading; an unknown
 * value draws a hatched empty track with the reason as text, never a zero.
 */
import { useId, type CSSProperties, type ReactNode } from 'react';

import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import styles from './EvidenceMeter.module.css';

export interface EvidenceMilestone {
  /** Where on the scale (same unit as `value`). */
  at: number;
  /** The milestone's name ("first read"): shown under its tick. */
  label: string;
}

export interface EvidenceMeterProps {
  /** Name of the evidence ("Closed trades"): shown above the track, names the meter. */
  label: string;
  /** Evidence collected so far; clamped to 0-`max` for the fill. Ignored while `state` is `unknown`. */
  value: number;
  /** Evidence needed (the end of the track). */
  max: number;
  /** Ticks on the track; one at or below `value` is reached. */
  milestones?: readonly EvidenceMilestone[];
  /** One line under the track (the projected date). */
  caption?: ReactNode;
  /** `known` (default) or `unknown`: no fill, a hatched track, the reason as text. */
  state?: 'known' | 'unknown';
  /** Why the evidence is not known ("No trades recorded yet"); shown instead of the reading. */
  unknownLabel?: string;
}

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export function EvidenceMeter({
  label,
  value,
  max,
  milestones = [],
  caption,
  state = 'known',
  unknownLabel = 'Not available',
}: EvidenceMeterProps) {
  const captionId = useId();
  const keyId = useId();
  const known = state === 'known' && !Number.isNaN(value);
  const top = Math.max(max, 0);
  const shown = known ? clamp(value, 0, top) : 0;
  const frac = (n: number) => (top > 0 ? clamp(n / top, 0, 1) : 0);
  const sorted = [...milestones]
    .filter((m) => m.at >= 0 && m.at <= top)
    .sort((a, b) => a.at - b.at);
  const reading = `${String(value)} of ${String(max)}`;
  const describedBy = [caption === undefined ? null : captionId, sorted.length > 0 ? keyId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={styles.root}>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        {known ? (
          <span className={styles.reading} aria-hidden="true">
            {reading}
          </span>
        ) : (
          <span className={styles.reason}>{unknownLabel}</span>
        )}
      </div>
      <div
        className={styles.track}
        data-unknown={!known || undefined}
        style={{ '--pos': `${String(frac(shown) * 100)}%` } as CSSProperties}
        {...(known
          ? {
              role: 'meter',
              'aria-label': label,
              'aria-valuemin': 0,
              'aria-valuemax': top,
              'aria-valuenow': shown,
              'aria-valuetext': reading,
              ...(describedBy ? { 'aria-describedby': describedBy } : {}),
            }
          : { role: 'img', 'aria-label': `${label}: unknown. ${unknownLabel}` })}
      >
        {known && <span className={styles.fill} />}
        {sorted.map((m) => (
          <span
            key={`${String(m.at)}-${m.label}`}
            className={styles.tick}
            data-reached={(known && value >= m.at) || undefined}
            aria-hidden="true"
            style={{ '--at': `${String(frac(m.at) * 100)}%` } as CSSProperties}
          />
        ))}
      </div>
      {sorted.length > 0 && (
        <>
          <div className={styles.names} aria-hidden="true">
            {sorted.map((m) => {
              const at = frac(m.at);
              return (
                <span
                  key={`${String(m.at)}-${m.label}`}
                  className={styles.name}
                  data-reached={(known && value >= m.at) || undefined}
                  data-align={at < 0.12 ? 'start' : at > 0.88 ? 'end' : 'center'}
                  style={{ '--at': `${String(at * 100)}%` } as CSSProperties}
                >
                  {m.at} {m.label}
                </span>
              );
            })}
          </div>
          <VisuallyHidden id={keyId}>
            {`Milestones: ${sorted
              .map(
                (m) =>
                  `${m.label} at ${String(m.at)}, ${known && value >= m.at ? 'reached' : 'not yet reached'}`,
              )
              .join('; ')}.`}
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
