/**
 * OutcomeDots: a row of small squares, one per item, each filled in the tone of its outcome (a
 * criterion passed, nearly passed, failed or had no value). The row is one image named by its
 * `label` and the items' labels in order ("Criteria: Price above 50-day: Passed, ..."), so colour
 * is never the only signal and nothing is counted: the caller says what each square means.
 */
import styles from './OutcomeDots.module.css';

/** The colour role of a square: pass, near miss or miss, or `muted` for "no value". */
export type OutcomeTone = 'positive' | 'warning' | 'negative' | 'muted';

export interface OutcomeDot {
  /** What the square stands for, with its outcome in words ("Price above 50-day: Passed"). */
  label: string;
  /** The square's colour role. */
  tone: OutcomeTone;
}

export interface OutcomeDotsProps {
  /** The squares, in order. */
  items: readonly OutcomeDot[];
  /** Accessible name of the row, e.g. "Criteria". */
  label: string;
}

export function OutcomeDots({ items, label }: OutcomeDotsProps) {
  const reading = items.length > 0 ? items.map((item) => item.label).join(', ') : 'none';
  return (
    <span className={styles.root} role="img" aria-label={`${label}: ${reading}`}>
      {items.map((item, index) => (
        <span key={index} className={styles.dot} data-tone={item.tone} />
      ))}
    </span>
  );
}
