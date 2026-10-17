/**
 * PartJoin: the connector between two parts of the trader's sentence in the Describe it review,
 * shown as text, not a card: the trader's own word ("but", "except", "or") beside the logic that
 * joins this part to the one before (AND, OR, AND NOT). OR and AND NOT carry their own tone so a
 * trader notices them; AND stays quiet. Read in order as "joined by but: AND". PartList places
 * it above the card it joins; labels arrive as props and an optional `info` slot holds a Guide
 * InfoButton.
 */
import type { ReactNode } from 'react';

import styles from './PartJoin.module.css';

/** The logic joining a part to the previous one: the values the server sends. */
export type PartJoinLogic = 'and' | 'or' | 'and_not';

export interface PartJoinProps {
  /** The logic joining this part to the previous one. */
  join: PartJoinLogic;
  /** The logic's label ("AND", "OR", "AND NOT"). */
  label: string;
  /** The trader's own connector ("but", "except"); omit when they wrote none. */
  words?: string | undefined;
  /** The lead-in of the spoken name ("joined by"). */
  joinedByLabel: string;
  /** A Guide InfoButton for the logic, shown after the label. */
  info?: ReactNode;
}

export function PartJoin({ join, label, words, joinedByLabel, info }: PartJoinProps) {
  const own = words?.trim();
  // The trader's word is shown only when it adds something to the label ("or" beside OR does not).
  const showWords = own !== undefined && own !== '' && own.toLowerCase() !== label.toLowerCase();
  const name = showWords ? `${joinedByLabel} ${own}: ${label}` : `${joinedByLabel} ${label}`;
  return (
    <div className={styles.join} data-join={join} role="group" aria-label={name}>
      {showWords ? <span className={styles.words}>{own}</span> : null}
      <span className={styles.label}>{label}</span>
      {info}
    </div>
  );
}
