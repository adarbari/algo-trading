/**
 * ShortLabel: a label with a shorter wording for a narrow container (a phone's top bar): the
 * full text shows where the container is 720 px or wider, `short` below it, by container query
 * (no measuring). `short` is decorative: the caller names the control with the full wording
 * (`aria-label`), so a screen reader hears the same on every width.
 */
import styles from './ShortLabel.module.css';

export interface ShortLabelProps {
  /** The full wording. */
  children: string;
  /** The wording under 720 px of container width. */
  short: string;
}

export function ShortLabel({ children, short }: ShortLabelProps) {
  return (
    <>
      <span className={styles.full}>{children}</span>
      <span className={styles.short} aria-hidden="true">
        {short}
      </span>
    </>
  );
}
