/**
 * Sparkline: a tiny inline line of a series' recent shape for a table cell or a stat (30 days of
 * closes, IV history). Plain SVG, no axes. Tone `auto` (default) draws it in the up / down colour
 * by the change from first to last value; or a series colour `s1`-`s6`, `muted`. An optional
 * dashed `baseline` (100 for a rebased series, 0 for a change) and a dot on the last value. It
 * is an image with a generated summary ("IV30, 30 values: 21.2% to 24.4%, low 19.8%, high
 * 25.1%"); missing values break the line. Fewer than two values show a muted dash.
 */
import { formatValue, type ValueFormat } from '../../format';
import type { Series } from '../../tokens';
import styles from './Sparkline.module.css';

export type SparklineTone = 'auto' | 'muted' | Series;

export interface SparklineProps {
  /** The values, oldest first; `null` is a gap. */
  values: readonly (number | null)[];
  /** What the line shows ("AAPL close, 30 days"): starts the accessible summary. */
  label: string;
  /** How values read in the summary (default a number with 2 decimals). */
  format?: ValueFormat;
  /** `auto` (up / down by first-to-last change, default), `muted`, or a series `s1`-`s6`. */
  tone?: SparklineTone;
  /** A dashed reference value (100 when rebased, 0 for changes). */
  baseline?: number;
  /** Width: `sm` 64 px, `md` 96 px (default), `lg` 128 px; height follows the text line. */
  width?: 'sm' | 'md' | 'lg';
  /** Mark the last value with a dot. */
  showLast?: boolean;
  /** Draw a placeholder while the values load. */
  loading?: boolean;
}

const VIEW_W = 100;
const VIEW_H = 24;
const PAD = 2;

/** SVG path for the values scaled into the view box; gaps (null) start a new segment. */
export function sparklinePath(
  values: readonly (number | null)[],
  min: number,
  max: number,
): string {
  const span = max - min || 1;
  const step = values.length > 1 ? VIEW_W / (values.length - 1) : 0;
  let path = '';
  let pen = false;
  values.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) {
      pen = false;
      return;
    }
    const x = index * step;
    const y = PAD + (1 - (value - min) / span) * (VIEW_H - PAD * 2);
    path += `${pen ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`;
    pen = true;
  });
  return path;
}

export function Sparkline({
  values,
  label,
  format = { kind: 'number', digits: 2 },
  tone = 'auto',
  baseline,
  width = 'md',
  showLast = false,
  loading = false,
}: SparklineProps) {
  if (loading) {
    return (
      <span className={styles.root} data-width={width} role="img" aria-label={`${label}: loading`}>
        <span className={styles.placeholder} />
      </span>
    );
  }
  const present = values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (present.length < 2) {
    return (
      <span className={styles.root} data-width={width} role="img" aria-label={`${label}: no data`}>
        <span className={styles.missing} aria-hidden="true">
          —
        </span>
      </span>
    );
  }
  const first = present[0] as number;
  const last = present.at(-1) as number;
  const low = Math.min(...present);
  const high = Math.max(...present);
  const min = baseline === undefined ? low : Math.min(low, baseline);
  const max = baseline === undefined ? high : Math.max(high, baseline);
  const fmt = (v: number) => formatValue(v, format).text;
  const resolved = tone === 'auto' ? (last > first ? 'up' : last < first ? 'down' : 'muted') : tone;
  const summary = `${label}, ${String(values.length)} values: ${fmt(first)} to ${fmt(last)}, low ${fmt(low)}, high ${fmt(high)}`;
  const lastIndex = values.length - 1 - [...values].reverse().findIndex((v) => v !== null);
  const span = max - min || 1;
  const step = values.length > 1 ? VIEW_W / (values.length - 1) : 0;
  const yOf = (v: number) => PAD + (1 - (v - min) / span) * (VIEW_H - PAD * 2);
  return (
    <span className={styles.root} data-width={width} role="img" aria-label={summary}>
      <svg
        className={styles.svg}
        viewBox={`0 0 ${String(VIEW_W)} ${String(VIEW_H)}`}
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        {baseline !== undefined && (
          <line
            className={styles.baseline}
            x1="0"
            x2={VIEW_W}
            y1={yOf(baseline)}
            y2={yOf(baseline)}
          />
        )}
        <path className={styles.line} data-tone={resolved} d={sparklinePath(values, min, max)} />
      </svg>
      {showLast && (
        <span
          className={styles.dot}
          data-tone={resolved}
          style={{
            insetInlineStart: `${String((lastIndex * step * 100) / VIEW_W)}%`,
            insetBlockStart: `${String((yOf(last) * 100) / VIEW_H)}%`,
          }}
        />
      )}
    </span>
  );
}
