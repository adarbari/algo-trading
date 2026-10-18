/**
 * ConditionGroup: a titled surface for a group of rule conditions (ADR 0071): the group's kind
 * label (all / any / none of), a title, an actions slot and an optional Guide InfoButton, then the
 * members as a vertical list with the PartJoin connector between them (and for all, or for any,
 * and not for none). One level only, so phones need no variant. `readOnly` shows a group the
 * Builder cannot edit (a deeper tree from Describe it or TOML) as one ExpandableRow: its
 * plain-English expression, members shown on expanding. Every label arrives as a prop.
 */
import { Children, useId, useState, type ReactNode } from 'react';

import { Heading } from '../../primitives/Heading';
import { Surface } from '../../primitives/Surface';
import { Text, type TextTone } from '../../primitives/Text';
import { ExpandableRow } from '../ExpandableRow';
import { PartJoin, type PartJoinLogic } from '../PartJoin';
import styles from './ConditionGroup.module.css';

/** How the members combine: every one, at least one, or none of them must hold. */
export type ConditionGroupKind = 'all' | 'any' | 'none';

const JOIN: Record<ConditionGroupKind, PartJoinLogic> = {
  all: 'and',
  any: 'or',
  none: 'and_not',
};

const TONE: Record<ConditionGroupKind, TextTone> = {
  all: 'muted',
  any: 'accent',
  none: 'negative',
};

export interface ConditionGroupProps {
  /** How the members combine. */
  kind: ConditionGroupKind;
  /** The kind in words ("All of", "Any of", "None of"). */
  kindLabel: string;
  /** The group's name; shown as a heading (a row title when read only). */
  title: ReactNode;
  /** The connector between members ("and", "or", "and not"). */
  connectorLabel: string;
  /** The spoken lead-in to the connector ("joined by"), hidden visually. */
  joinedByLabel: string;
  /** Controls on the header's end (buttons, a Guide InfoButton). Edit mode only. */
  actions?: ReactNode;
  /** A Guide InfoButton for the kind, shown beside the title. */
  info?: ReactNode;
  /** The group as one plain-English sentence; shown on the read-only row. */
  expression?: ReactNode;
  /** Show one expandable row with no editing controls. */
  readOnly?: boolean;
  /** Read only: start expanded. */
  defaultOpen?: boolean;
  /** Heading level in the page outline; 3 by default. */
  headingLevel?: 2 | 3 | 4;
  /** The members, in order. */
  children: ReactNode;
}

export function ConditionGroup({
  kind,
  kindLabel,
  title,
  connectorLabel,
  joinedByLabel,
  actions,
  info,
  expression,
  readOnly = false,
  defaultOpen = false,
  headingLevel = 3,
  children,
}: ConditionGroupProps) {
  const headingId = useId();
  const [open, setOpen] = useState(defaultOpen);
  const members = (
    <ol className={styles.members} aria-label={readOnly && typeof title === 'string' ? title : undefined}>
      {Children.toArray(children).map((child, index) => (
        <li className={styles.member} key={index}>
          {index > 0 ? (
            <PartJoin
              join={JOIN[kind]}
              label={connectorLabel}
              joinedByLabel={joinedByLabel}
              readAsLabel=""
            />
          ) : null}
          {child}
        </li>
      ))}
    </ol>
  );
  if (readOnly) {
    return (
      <div className={styles.readonly} data-kind={kind}>
        <ExpandableRow
          title={
            <>
              {title}
              {expression !== undefined && (
                <>
                  {' '}
                  <span className={styles.expression}>{expression}</span>
                </>
              )}
            </>
          }
          badge={kindLabel}
          open={open}
          onOpenChange={setOpen}
        >
          {members}
        </ExpandableRow>
      </div>
    );
  }
  return (
    <Surface as="section" aria-labelledby={headingId} tone="row" padding={3}>
      <div className={styles.header} data-kind={kind}>
        <div className={styles.titles}>
          <Text size="sm" weight="semibold" tone={TONE[kind]}>
            {kindLabel}
          </Text>
          <Heading level={headingLevel} id={headingId}>
            {title}
          </Heading>
          {info}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
      {members}
    </Surface>
  );
}
