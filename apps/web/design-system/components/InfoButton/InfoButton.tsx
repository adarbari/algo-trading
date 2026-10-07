/**
 * InfoButton: a small "what is this?" button placed beside the thing it explains (a column
 * header, a card title, a criterion's field). It opens the explanation (the app wires `onClick`
 * to a HelpDrawer); `summary` adds a one-sentence Tooltip on hover and focus, and `expanded`
 * marks the button pressed while that explanation is open. Compact: it adds no height to a
 * table header row. `label` is the accessible name.
 */
import type { MouseEventHandler, Ref } from 'react';

import { Icon } from '../Icon';
import { Tooltip } from '../Tooltip';
import styles from './InfoButton.module.css';

export interface InfoButtonProps {
  /** The accessible name, naming the thing explained ("What is rel_volume?"). */
  label: string;
  /** One sentence shown in a tooltip on hover and keyboard focus. */
  summary?: string;
  /** The explanation is open: sets `aria-expanded` and the pressed style. Omit when it never expands. */
  expanded?: boolean | undefined;
  onClick?: MouseEventHandler<HTMLButtonElement>;
  ref?: Ref<HTMLButtonElement>;
}

export function InfoButton({ label, summary, expanded, onClick, ref }: InfoButtonProps) {
  const button = (describedBy?: string) => (
    <button
      ref={ref}
      type="button"
      className={styles.infoButton}
      aria-label={label}
      aria-describedby={describedBy}
      aria-expanded={expanded}
      data-expanded={expanded || undefined}
      // The native title would show beside the Tooltip; it stays only when there is no summary.
      title={summary ? undefined : label}
      onClick={onClick}
    >
      <Icon name="info" size="sm" />
    </button>
  );
  if (!summary) return button();
  return <Tooltip content={summary}>{(props) => button(props['aria-describedby'])}</Tooltip>;
}
