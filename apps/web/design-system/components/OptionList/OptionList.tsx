/**
 * OptionList: a scrolling list of choices, each a short name (optionally monospace, for field
 * and symbol names) over a one-line description, one of them the current choice. A choice is a
 * button; the current one carries `aria-current` and the accent tint, so colour is never the only
 * signal (the selected row is also announced). Controlled: `value` in, `onSelect(id)` out. Taller
 * than `maxHeight` it scrolls inside itself, so it never grows a page; loading shows
 * placeholders, an empty list shows the empty message. For a choice made once and closed use
 * Select; for many choices to filter use Combobox. With `values` it is a multi-select: each
 * option is a toggle (`aria-pressed`, a check mark) and `count` shows how many rows hold it.
 * `variant="card"` lays the choices out as bordered cards in a responsive grid (a way in, an
 * onboarding choice): the same buttons, the title larger, the description under it.
 */
import type { ReactNode } from 'react';

import { formatValue } from '../../format';
import { EmptyState } from '../EmptyState';
import { Icon } from '../Icon';
import { Skeleton } from '../Skeleton';
import styles from './OptionList.module.css';

export interface OptionListItem {
  /** Stable unique id (reported to `onSelect`). */
  id: string;
  /** The choice's name. */
  title: string;
  /** One line on what it is. */
  description?: string;
  /** How many rows hold this value (shown after the title, tabular). */
  count?: number;
}

export interface OptionListProps {
  items: readonly OptionListItem[];
  /** The id of the current choice (null: none). Ignored when `values` is given. */
  value: string | null;
  /** Multi-select: the ids in force. Options become toggles; `onSelect` reports the id toggled. */
  values?: readonly string[];
  onSelect: (id: string) => void;
  /** Accessible name of the list ("Fields in Volatility"). */
  label: string;
  /** Titles in the monospace face (catalogue names, symbols). */
  mono?: boolean;
  /** Scroll inside the list taller than this: `md` (360 px) or `lg` (560 px); none by default. */
  maxHeight?: 'md' | 'lg';
  /** Placeholders while the items load. */
  loading?: boolean;
  /** Shown when there are no items. */
  emptyMessage?: ReactNode;
  /** `list` (default): rows; `card`: bordered cards in a grid that wraps to the width. */
  variant?: 'list' | 'card';
}

export function OptionList({
  items,
  value,
  values,
  onSelect,
  label,
  mono = false,
  maxHeight,
  loading = false,
  emptyMessage = 'Nothing to choose.',
  variant = 'list',
}: OptionListProps) {
  if (loading) return <Skeleton lines={5} label={`Loading ${label}`} />;
  if (items.length === 0) return <EmptyState compact title={emptyMessage} />;
  return (
    <ul
      className={styles.list}
      aria-label={label}
      data-max-height={maxHeight}
      data-variant={variant}
    >
      {items.map((item) => {
        const multi = values !== undefined;
        const on = multi ? values.includes(item.id) : item.id === value;
        return (
          <li key={item.id}>
            <button
              type="button"
              className={styles.option}
              aria-current={!multi && on ? 'true' : undefined}
              aria-pressed={multi ? on : undefined}
              data-on={multi && on ? true : undefined}
              onClick={() => {
                onSelect(item.id);
              }}
            >
              <span className={styles.head}>
                {multi && (
                  <span className={styles.check}>
                    <Icon name="check" size="sm" tone={on ? 'accent' : 'inherit'} />
                  </span>
                )}
                <span className={styles.title} data-mono={mono || undefined}>
                  {item.title}
                </span>
                {item.count !== undefined && (
                  <span className={styles.count}>
                    {formatValue(item.count, { kind: 'number' }).text}
                  </span>
                )}
              </span>
              {item.description !== undefined && (
                <span className={styles.description}>{item.description}</span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
