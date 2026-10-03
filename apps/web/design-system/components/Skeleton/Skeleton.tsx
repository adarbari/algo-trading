/**
 * Skeleton: placeholder shapes in the track colour while content loads, laid out like the
 * content to come so the page does not jump: `text` (lines, the last one shorter), `rect` (a
 * chart or an image area) or `table` (rows of cells at the density's row height). A slow pulse,
 * none under reduced motion. Announced once as busy with `label` ("Loading ideas…"); the shapes
 * themselves are hidden from screen readers.
 */
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import styles from './Skeleton.module.css';

export interface SkeletonProps {
  /** The shape: `text` lines (default), a `rect` block, or `table` rows. */
  variant?: 'text' | 'rect' | 'table';
  /** Lines of text (default 3). */
  lines?: number;
  /** Rows (default 5) and columns (default 4) of a `table` skeleton. */
  rows?: number;
  columns?: number;
  /** Height of a `rect`: `sm`, `md` (default, a chart) or `lg`. */
  height?: 'sm' | 'md' | 'lg';
  /** What is loading, for screen readers. */
  label?: string;
}

const range = (n: number) => Array.from({ length: Math.max(0, n) }, (_, i) => i);

export function Skeleton({
  variant = 'text',
  lines = 3,
  rows = 5,
  columns = 4,
  height = 'md',
  label = 'Loading…',
}: SkeletonProps) {
  return (
    <div className={styles.root} role="status" aria-busy="true" data-variant={variant}>
      <VisuallyHidden>{label}</VisuallyHidden>
      {variant === 'text' &&
        range(lines).map((i) => (
          <span
            key={i}
            className={styles.line}
            data-last={(i === lines - 1 && lines > 1) || undefined}
            aria-hidden="true"
          />
        ))}
      {variant === 'rect' && (
        <span className={styles.rect} data-height={height} aria-hidden="true" />
      )}
      {variant === 'table' &&
        range(rows).map((r) => (
          <span key={r} className={styles.row} aria-hidden="true">
            {range(columns).map((c) => (
              <span key={c} className={styles.cell} data-first={c === 0 || undefined} />
            ))}
          </span>
        ))}
    </div>
  );
}
