/**
 * TextBlock: a block of raw text shown as written (a model's answer, an error message, a log
 * excerpt): monospace, line breaks and spaces kept, long lines wrapped, and a height cap past
 * which it scrolls. The block is a read-only text box that takes the keyboard focus so it can be
 * scrolled without a mouse; `label` names it for a screen reader. Never for text a reader is meant to read as prose
 * (Text) or for a value in a row (Mono).
 */
import styles from './TextBlock.module.css';

export interface TextBlockProps {
  /** The text, shown as given (null or empty: the `empty` words). */
  text: string | null | undefined;
  /** What the text is ("Raw model answer"); required: it is the block's accessible name. */
  label: string;
  /** The height before it scrolls: `sm` about 8 lines, `md` (default) about 16. */
  size?: 'sm' | 'md';
  /** What reads when there is no text (default "nothing"). */
  empty?: string;
}

export function TextBlock({ text, label, size = 'md', empty = 'nothing' }: TextBlockProps) {
  const present = text !== null && text !== undefined && text !== '';
  return (
    <div
      className={styles.block}
      role="textbox"
      aria-readonly="true"
      aria-multiline="true"
      aria-label={label}
      tabIndex={0}
      data-size={size}
      data-empty={present ? undefined : true}
    >
      {present ? text : empty}
    </div>
  );
}
