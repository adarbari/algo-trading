/**
 * ProseList: a bulleted (or numbered) list of sentences, each optionally opening with a bold
 * lead-in ("It is small and spread out."): the form of a "why it survives" or "how to tell a
 * real one" list in a reference page. Items hold running text (a ReactNode, so a citation link
 * can sit in it); a short list of values is a KeyValue, a table a DataTable.
 */
import type { ReactNode } from 'react';

import { Text } from '../../primitives/Text';
import styles from './ProseList.module.css';

export interface ProseListItem {
  /** Stable key of the item. */
  id: string;
  /** The bold opening words, the item's point in a few words. */
  lead?: string;
  /** The rest of the item. */
  body: ReactNode;
}

export interface ProseListProps {
  items: readonly ProseListItem[];
  /** Numbered instead of bulleted (a fixed order the reader follows). */
  ordered?: boolean;
  /** Accessible name of the list, when the surrounding heading does not name it. */
  'aria-label'?: string;
}

export function ProseList({ items, ordered = false, 'aria-label': ariaLabel }: ProseListProps) {
  if (items.length === 0) return null;
  const List = ordered ? 'ol' : 'ul';
  return (
    <List className={styles.list} aria-label={ariaLabel} data-ordered={ordered || undefined}>
      {items.map((item) => (
        <li key={item.id} className={styles.item}>
          {item.lead !== undefined && (
            <>
              <Text weight="semibold">{item.lead}</Text>{' '}
            </>
          )}
          <Text tone="secondary">{item.body}</Text>
        </li>
      ))}
    </List>
  );
}
