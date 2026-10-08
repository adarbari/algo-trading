/**
 * SearchDialog: a modal search (the ⌘K palette) over results the caller supplies, grouped by
 * kind. The caller owns the query and the lookup (nothing is ranked or filtered here): this
 * shows the box, the groups and the states (a hint before anything is typed, a skeleton while
 * reading, no matches, an error with a retry). Each result is a real link (`href`), so it can be
 * opened in a new tab; a plain click and Enter call `onSelect` instead. Keyboard: ArrowDown from
 * the box moves focus to the first result, ArrowDown / ArrowUp walk the results (ArrowUp from the
 * first returns to the box), Enter in the box opens the first result (once the results for what
 * was typed have arrived), Escape closes.
 */
import { useEffect, useRef, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react';

import { Text } from '../../primitives/Text';
import { Dialog } from '../Dialog';
import { EmptyState } from '../EmptyState';
import { ErrorState } from '../ErrorState';
import { KeyHints } from '../KeyHints';
import { SearchInput } from '../SearchInput';
import { Skeleton } from '../Skeleton';
import styles from './SearchDialog.module.css';

export interface SearchDialogItem {
  /** Stable key within its group. */
  id: string;
  /** The result's name. */
  title: string;
  /** A line of its text around the match. */
  snippet?: string;
  /** Where it opens. */
  href: string;
}

export interface SearchDialogGroup {
  id: string;
  /** The group's heading ("Fields", "Glossary"). */
  title: string;
  items: readonly SearchDialogItem[];
}

export interface SearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The dialog's accessible name ("Search the Guide"). */
  title: string;
  /** The query (controlled). */
  query: string;
  onQueryChange: (query: string) => void;
  placeholder?: string;
  /** The results by group, in the order to show them. */
  groups: readonly SearchDialogGroup[];
  /** A read is in flight. */
  loading?: boolean;
  /** The last read failed; `onRetry` reads again. */
  error?: boolean;
  onRetry?: () => void;
  /** Shown while the query is empty. */
  hint?: ReactNode;
  /** Called when a result is chosen (click or Enter); the caller closes and navigates. */
  onSelect: (item: SearchDialogItem) => void;
}

export function SearchDialog({
  open,
  onOpenChange,
  title,
  query,
  onQueryChange,
  placeholder,
  groups,
  loading = false,
  error = false,
  onRetry,
  hint,
  onSelect,
}: SearchDialogProps) {
  const results = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const enterPending = useRef(false);
  const typed = query.trim() !== '';
  const shown = groups.filter((g) => g.items.length > 0);

  const links = () =>
    Array.from(results.current?.querySelectorAll<HTMLAnchorElement>('a[href]') ?? []);

  const onBoxKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const first = links()[0];
    if (event.key === 'ArrowDown' && first) {
      event.preventDefault();
      first.focus();
    } else if (event.key === 'Enter' && typed) {
      event.preventDefault();
      // Results still on their way (the query just changed): open the first one when they land.
      if (loading) enterPending.current = true;
      else first?.click();
    }
  };

  useEffect(() => {
    if (loading || !enterPending.current) return;
    enterPending.current = false;
    links()[0]?.click();
  });

  const onResultsKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    const all = links();
    const at = all.indexOf(document.activeElement as HTMLAnchorElement);
    if (event.key === 'ArrowDown') all[Math.min(at + 1, all.length - 1)]?.focus();
    else if (at <= 0) box.current?.querySelector('input')?.focus();
    else all[at - 1]?.focus();
  };

  const choose = (item: SearchDialogItem) => (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onSelect(item);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} size="lg">
      <div className={styles.body}>
        <div ref={box} role="presentation" onKeyDown={onBoxKeyDown}>
          <SearchInput
            aria-label={title}
            {...(placeholder ? { placeholder } : {})}
            value={query}
            onValueChange={(next) => {
              enterPending.current = false;
              onQueryChange(next);
            }}
            loading={loading && shown.length > 0}
          />
        </div>
        <div
          className={styles.results}
          ref={results}
          role="presentation"
          onKeyDown={onResultsKeyDown}
          aria-live="polite"
        >
          {!typed ? (
            hint ? (
              <Text size="sm" tone="muted">
                {hint}
              </Text>
            ) : null
          ) : error ? (
            <ErrorState title="The search failed." compact {...(onRetry ? { onRetry } : {})} />
          ) : shown.length > 0 ? (
            shown.map((group) => (
              <section key={group.id} className={styles.group} aria-label={group.title}>
                <h3 className={styles.groupTitle}>{group.title}</h3>
                <ul className={styles.list}>
                  {group.items.map((item) => (
                    <li key={item.id}>
                      <a className={styles.item} href={item.href} onClick={choose(item)}>
                        <span className={styles.title}>{item.title}</span>
                        {item.snippet && <span className={styles.snippet}>{item.snippet}</span>}
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          ) : loading ? (
            <Skeleton label="Searching" />
          ) : (
            <EmptyState compact icon="search" title={`Nothing matches “${query.trim()}”.`} />
          )}
        </div>
        <div className={styles.hints}>
          <KeyHints
            hints={[
              { keys: ['↓', '↑'], label: 'move' },
              { keys: ['Enter'], label: 'open' },
              { keys: ['Esc'], label: 'close' },
            ]}
          />
        </div>
      </div>
    </Dialog>
  );
}
