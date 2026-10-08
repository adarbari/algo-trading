/**
 * OddsLine: an edge's evidence for a pick in one line: hit rate against the base rate, the lift,
 * the independent sessions behind them, optionally the picks and the run it came from. The hit
 * rate, base rate and sessions are required together, so a bare hit rate cannot be shown. An
 * exploratory run (read outside the frozen period) carries a visible EXPLORATORY badge. States:
 * loading (placeholder), empty (no run yet) and error (the evidence failed to load). Explanations
 * are not written here: the `info` slot takes an InfoButton given a Guide entry. It wraps in a
 * narrow container.
 */
import type { ReactNode } from 'react';

import { formatValue } from '../../format';
import { Text } from '../../primitives/Text';
import { Skeleton } from '../Skeleton';
import { StatusBadge } from '../StatusBadge';
import styles from './OddsLine.module.css';

interface OddsLineBase {
  /** The run the figures come from (a run id or date): shown muted at the end. */
  runLabel?: string;
  /** The Guide's InfoButton for this line (the app supplies it; no explanation text lives here). */
  info?: ReactNode;
}

export interface OddsLineReady extends OddsLineBase {
  state?: 'ready';
  /** Share of picks that hit, as a fraction (0.62). Required with the base rate and sessions. */
  hitRate: number;
  /** The share that hit with no edge, as a fraction (0.51): the comparison for the hit rate. */
  baseRate: number;
  /** Independent sessions the figures rest on. */
  sessions: number;
  /** Hit rate over base rate; written when given, never derived here. */
  lift?: number;
  /** How many picks the hit rate counts. */
  picks?: number;
  /** The run was read outside the frozen period: shown as EXPLORATORY, never as evidence. */
  exploratory?: boolean;
}

export interface OddsLineNotReady extends OddsLineBase {
  /** `loading` shows a placeholder, `empty` that no run exists yet, `error` that it failed. */
  state: 'loading' | 'empty' | 'error';
  /** Replaces the default words of the empty and error states. */
  message?: string;
}

export type OddsLineProps = OddsLineReady | OddsLineNotReady;

const percent = (value: number) => formatValue(value, { kind: 'percent', digits: 1 }).text;
const count = (value: number) => formatValue(value, { kind: 'number' }).text;

function Part({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className={styles.part}>
      <Text size="sm" tone="muted">
        {label}
      </Text>
      <span className={styles.value}>{children}</span>
    </span>
  );
}

function NotReady({ state, message, info }: OddsLineNotReady) {
  if (state === 'loading') return <Skeleton lines={1} label="Loading odds…" />;
  const failed = state === 'error';
  return (
    <p className={styles.root} data-state={state} role={failed ? 'alert' : undefined}>
      <Text size="sm" tone={failed ? 'negative' : 'muted'}>
        {message ?? (failed ? 'Odds failed to load' : 'No run yet')}
      </Text>
      {info}
    </p>
  );
}

export function OddsLine(props: OddsLineProps) {
  if (!('hitRate' in props)) return <NotReady {...props} />;
  const { hitRate, baseRate, sessions, lift, picks, exploratory, runLabel, info } = props;
  return (
    <p className={styles.root} data-state="ready" data-exploratory={exploratory || undefined}>
      {exploratory && (
        <StatusBadge tone="warning" title="Read outside the frozen period">
          EXPLORATORY
        </StatusBadge>
      )}
      <Part label="Hit rate">
        <Text size="sm" weight="semibold">
          {percent(hitRate)}
        </Text>
        <Text size="sm" tone="muted">{`vs ${percent(baseRate)} base`}</Text>
      </Part>
      {lift !== undefined && (
        <Part label="Lift">
          <Text size="sm">{`${formatValue(lift, { kind: 'number', digits: 2 }).text}×`}</Text>
        </Part>
      )}
      <Part label="Sessions">
        <Text size="sm">{count(sessions)}</Text>
      </Part>
      {picks !== undefined && (
        <Part label="Picks">
          <Text size="sm">{count(picks)}</Text>
        </Part>
      )}
      {runLabel !== undefined && <Text size="sm" tone="muted">{`· ${runLabel}`}</Text>}
      {info}
    </p>
  );
}
