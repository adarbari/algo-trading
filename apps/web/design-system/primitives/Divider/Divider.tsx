/**
 * Divider: a 1 px rule between groups. Horizontal is an `<hr>`; vertical (between toolbar
 * groups) is a separator that stretches to the row's height. `soft` for rules inside a panel.
 */
import styles from './Divider.module.css';

export interface DividerProps {
  /** `horizontal` (an hr between stacked groups) or `vertical` (between items in a row). */
  orientation?: 'horizontal' | 'vertical';
  /** `default` (panel borders) or `soft` (inside a panel). */
  tone?: 'default' | 'soft';
  /** Purely visual: hidden from assistive technology. */
  decorative?: boolean;
}

export function Divider({
  orientation = 'horizontal',
  tone = 'default',
  decorative = false,
}: DividerProps) {
  if (orientation === 'horizontal') {
    return (
      <hr
        className={styles.divider}
        data-orientation={orientation}
        data-tone={tone}
        aria-hidden={decorative || undefined}
      />
    );
  }
  return (
    <div
      className={styles.divider}
      data-orientation={orientation}
      data-tone={tone}
      role={decorative ? 'presentation' : 'separator'}
      aria-orientation={decorative ? undefined : 'vertical'}
    />
  );
}
