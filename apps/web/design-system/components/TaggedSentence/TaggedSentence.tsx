/**
 * TaggedSentence: a sentence the trader typed, shown as inline spans that each say how it was
 * understood: `applied` (a stored field, solid underline), `formula` (a draft formula to review,
 * dashed), `ask` (needs the trader's call, wavy), `gap` (not available yet, dotted) or `plain`
 * (no tag). A tagged span carries its short label beside it as text, so the kind is never
 * colour alone: the underline style and the label say it too. It wraps like prose, so it works
 * at phone width. Read as one sentence by assistive technology, with each label after its words.
 * Text and labels arrive as props; this component writes none.
 */
import styles from './TaggedSentence.module.css';

export type SentenceKind = 'applied' | 'formula' | 'ask' | 'gap' | 'plain';

export interface SentenceSegment {
  /** Stable key (defaults to the position). */
  id?: string;
  /** The words, exactly as typed. */
  text: string;
  /** How the words were understood. */
  kind: SentenceKind;
  /** The short tag shown beside the words ("applied", "formula"); required for every kind but `plain`. */
  label?: string;
}

export interface TaggedSentenceProps {
  /** The sentence, in order; the spans concatenate to what the trader typed. */
  segments: readonly SentenceSegment[];
  /** Accessible name of the sentence ("What was understood"). */
  'aria-label'?: string;
}

export function TaggedSentence({ segments, 'aria-label': ariaLabel }: TaggedSentenceProps) {
  return (
    <p className={styles.sentence} aria-label={ariaLabel}>
      {segments.map((segment, index) => (
        <span key={segment.id ?? index}>
          {index > 0 && ' '}
          {segment.kind === 'plain' ? (
            <span className={styles.plain}>{segment.text}</span>
          ) : (
            <span className={styles.span} data-kind={segment.kind}>
              <span className={styles.words}>{segment.text}</span>
              {segment.label && <span className={styles.label}> {segment.label}</span>}
            </span>
          )}
        </span>
      ))}
    </p>
  );
}
