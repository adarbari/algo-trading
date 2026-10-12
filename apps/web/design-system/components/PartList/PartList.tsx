/**
 * PartList: the ordered PartCards of one sentence, in the order the trader wrote the parts, a
 * token gap apart. A card for words that were not understood, or the "kept from your screen"
 * card, sits in the list like any other. A list element, so assistive technology announces
 * "list, N items"; its name arrives as a prop.
 */
import { Children, type ReactNode } from 'react';

import styles from './PartList.module.css';

export interface PartListProps {
  /** Accessible name of the list ("Parts of your sentence"). */
  'aria-label': string;
  /** The PartCards, in order. */
  children: ReactNode;
}

export function PartList({ 'aria-label': ariaLabel, children }: PartListProps) {
  return (
    <ol className={styles.list} aria-label={ariaLabel}>
      {Children.toArray(children).map((child, index) => (
        <li className={styles.item} key={index}>
          {child}
        </li>
      ))}
    </ol>
  );
}
