/**
 * PartList: the ordered PartCards of one sentence, in the order the trader wrote the parts, a
 * token gap apart. A card for words that were not understood, or the "kept from your screen"
 * card, sits in the list like any other. A list element, so assistive technology announces
 * "list, N items"; its name arrives as a prop. A PartJoin child is not an item of its own: it
 * is placed above the card that follows it, inside that card's item, so the count stays the
 * number of parts and the connector is read just before the part it joins.
 */
import { Children, isValidElement, type ReactNode } from 'react';

import { PartJoin } from '../PartJoin';
import styles from './PartList.module.css';

export interface PartListProps {
  /** Accessible name of the list ("Parts of your sentence"). */
  'aria-label': string;
  /**
   * The PartCards, in order; a PartJoin before a card joins it to the previous one. Pass the
   * PartJoin directly, unwrapped: a wrapper component hides it from the list and it becomes an item.
   * A trailing PartJoin has no card to join and is dropped (with a warning in development).
   */
  children: ReactNode;
}

export function PartList({ 'aria-label': ariaLabel, children }: PartListProps) {
  const items: { key: string | number; join?: ReactNode; card: ReactNode }[] = [];
  let pending: ReactNode = null;
  for (const [index, child] of Children.toArray(children).entries()) {
    if (isValidElement(child) && child.type === PartJoin) {
      pending = child;
      continue;
    }
    const key = isValidElement(child) && child.key !== null ? child.key : index;
    items.push({ key, join: pending, card: child });
    pending = null;
  }
  if (pending !== null && import.meta.env.DEV) {
    // eslint-disable-next-line no-console -- a development-only misuse warning
    console.warn('PartList: a trailing PartJoin has no card after it and was dropped.');
  }
  return (
    <ol className={styles.list} aria-label={ariaLabel}>
      {items.map(({ key, join, card }) => (
        <li className={styles.item} key={key}>
          {join}
          {card}
        </li>
      ))}
    </ol>
  );
}
