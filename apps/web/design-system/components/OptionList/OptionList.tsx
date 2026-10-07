/**
 * OptionList: a scrolling list of choices, each a short name (optionally monospace, for field
 * and symbol names) over a one-line description, one of them the current choice. A choice is a
 * button; the current one carries `aria-current` and the accent tint, so colour is never the only
 * signal (the selected row is also announced). Controlled: `value` in, `onSelect(id)` out. Taller
 * than `maxHeight` it scrolls inside itself, so it never grows a page; loading shows
 * placeholders, an empty list shows the empty message. For a choice made once and closed use
 * Select; for many choices to filter use Combobox.
 */
import type { ReactNode } from 'react';

import { EmptyState } from '../EmptyState';
import { Skeleton } from '../Skeleton';
import styles from './OptionList.module.css';

export interface OptionListItem {
  /** Stable unique id (reported to `onSelect`). */
  id: string;
  /** The choice's name. */
  title: string;
  /** One line on what it is. */
  description?: string;
}

export interface OptionListProps {
  items: readonly OptionListItem[];
  /** The id of the current choice (null: none). */
  value: string | null;
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
}

export function OptionList({
  items,
  value,
  onSelect,
  label,
  mono = false,
  maxHeight,
  loading = false,
  emptyMessage = 'Nothing to choose.',
}: OptionListProps) {
  if (loading) return <Skeleton lines={5} label={`Loading ${label}`} />;
  if (items.length === 0) return <EmptyState compact title={emptyMessage} />;
  return (
    <ul className={styles.list} aria-label={label} data-max-height={maxHeight}>
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            className={styles.option}
            aria-current={item.id === value ? 'true' : undefined}
            onClick={() => {
              onSelect(item.id);
            }}
          >
            <span className={styles.title} data-mono={mono || undefined}>
              {item.title}
            </span>
            {item.description !== undefined && (
              <span className={styles.description}>{item.description}</span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
