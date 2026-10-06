/**
 * IndicatorRow: one row of an indicator list: a status (a StatusBadge, or a dot for a dense
 * list) with its text, a plain-language name with the technical name muted beside it, a one-line
 * description, and the current value with its unit at the right, plus an optional "changed"
 * marker (up, down or new; its words are for screen readers). Given children it becomes an
 * expandable row built on Disclosure: the whole header is one button that toggles the detail
 * (why it matters, what it did before, links). Without children it is a plain row. Put rows in
 * a list element of the caller's; compact and comfortable follow the density tokens.
 */
import type { ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import { Text } from '../../primitives/Text';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { Disclosure } from '../Disclosure';
import { Icon } from '../Icon';
import { toneStyles } from '../Legend';
import { Skeleton } from '../Skeleton';
import { StatusBadge, type StatusTone } from '../StatusBadge';
import styles from './IndicatorRow.module.css';

/** How an indicator moved since the last look: `up`, `down`, or `new` (first time shown). */
export type IndicatorChange = 'up' | 'down' | 'new';

export interface IndicatorStatus {
  /** Tone of the badge or dot (the StatusBadge tones). */
  tone: StatusTone;
  /** The state, in words ("On", "Off", "Watch"): always shown or read, colour only reinforces it. */
  label: string;
}

export interface IndicatorRowProps {
  /** The state of the indicator. */
  status: IndicatorStatus;
  /** `badge` (default, the state as a StatusBadge) or `dot` (a dense list: a dot, the state read aloud). */
  indicator?: 'badge' | 'dot';
  /** The plain-language name ("Are banks still lending?"). */
  name: string;
  /** The technical name, muted beside the plain one ("Senior loan officer survey"). */
  technicalName?: string;
  /** One line on what it measures. */
  description?: ReactNode;
  /** The current value; `null` shows an em dash, omitted shows no value. */
  value?: number | string | null;
  /** The unit after the value ("bp", "pts", "%"). */
  unit?: string;
  /** How a numeric value reads (default `text`: as given). */
  format?: ValueFormat;
  /** The change marker. */
  changed?: IndicatorChange;
  /** What the marker says to a screen reader (default "Increased", "Decreased" or "New"). */
  changedLabel?: string;
  /** The detail shown when expanded; without it the row is not expandable. */
  children?: ReactNode;
  /** Controlled open state (pair with `onOpenChange`). */
  open?: boolean;
  /** Initial open state when uncontrolled. */
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Placeholder while the row loads. */
  loading?: boolean;
}

const CHANGE_WORDS: Record<IndicatorChange, string> = {
  up: 'Increased',
  down: 'Decreased',
  new: 'New',
};

export function IndicatorRow({
  status,
  indicator = 'badge',
  name,
  technicalName,
  description,
  value,
  unit,
  format,
  changed,
  changedLabel,
  children,
  open,
  defaultOpen,
  onOpenChange,
  loading = false,
}: IndicatorRowProps) {
  if (loading) {
    return (
      <div className={styles.root}>
        <Skeleton lines={2} label={`Loading ${name}`} />
      </div>
    );
  }

  const head = (
    <span className={styles.head}>
      <span className={styles.status}>
        {indicator === 'badge' ? (
          <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
        ) : (
          <>
            <span
              className={`${styles.dot} ${toneStyles.tone}`}
              data-tone={status.tone}
              aria-hidden="true"
            />
            <VisuallyHidden>{`${status.label}: `}</VisuallyHidden>
          </>
        )}
      </span>
      <span className={styles.text}>
        <span className={styles.names}>
          <Text weight="medium">{name}</Text>
          {technicalName !== undefined && (
            <Text size="sm" tone="muted">
              {technicalName}
            </Text>
          )}
        </span>
        {description !== undefined && (
          <Text size="sm" tone="secondary">
            {description}
          </Text>
        )}
      </span>
    </span>
  );

  const reading =
    value === undefined && changed === undefined ? undefined : (
      <span className={styles.reading}>
        {value !== undefined && (
          <span className={styles.value} data-missing={value === null || undefined}>
            {formatValue(value, format).text}
            {unit !== undefined && value !== null && (
              <span className={styles.unit}>{` ${unit}`}</span>
            )}
          </span>
        )}
        {changed !== undefined && (
          <span className={styles.changed} data-change={changed}>
            {changed === 'new' ? (
              <span aria-hidden="true">NEW</span>
            ) : (
              <Icon name={changed === 'up' ? 'chevron-up' : 'chevron-down'} size="sm" />
            )}
            <VisuallyHidden>{`. ${changedLabel ?? CHANGE_WORDS[changed]}`}</VisuallyHidden>
          </span>
        )}
      </span>
    );

  if (children === undefined) {
    return (
      <div className={styles.root}>
        <div className={styles.flat}>
          {head}
          {reading}
        </div>
      </div>
    );
  }
  return (
    <div className={styles.root}>
      <Disclosure
        variant="plain"
        label={head}
        {...(reading === undefined ? {} : { count: reading })}
        {...(open === undefined ? {} : { open })}
        {...(defaultOpen === undefined ? {} : { defaultOpen })}
        {...(onOpenChange === undefined ? {} : { onOpenChange })}
      >
        {children}
      </Disclosure>
    </div>
  );
}
