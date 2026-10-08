/**
 * TrackRecordChip: a screener's track record in one small badge: `evidenced` (an edge passed the
 * frozen period), `candidate` with the independent sessions so far, or `not-run`. A figure from
 * an exploratory run never feeds it: `exploratory` renders nothing at all. The state is always
 * in words; colour only reinforces it. Not interactive.
 */
import styles from './TrackRecordChip.module.css';
import { StatusBadge, type StatusTone } from '../StatusBadge';

export type TrackRecordStatus = 'evidenced' | 'candidate' | 'not-run';

export interface TrackRecordChipProps {
  /** `evidenced`, `candidate` or `not-run`. */
  status: TrackRecordStatus;
  /** Independent sessions behind a `candidate` (written as "Candidate · 42 sessions"). */
  sessions?: number;
  /** The record comes from an exploratory run: nothing is rendered. */
  exploratory?: boolean;
}

const TONE: Record<TrackRecordStatus, StatusTone> = {
  evidenced: 'positive',
  candidate: 'info',
  'not-run': 'neutral',
};

function words(status: TrackRecordStatus, sessions: number | undefined): string {
  if (status === 'evidenced') return 'Evidenced';
  if (status === 'not-run') return 'Not run';
  if (sessions === undefined) return 'Candidate';
  return `Candidate · ${sessions} ${sessions === 1 ? 'session' : 'sessions'}`;
}

export function TrackRecordChip({ status, sessions, exploratory = false }: TrackRecordChipProps) {
  if (exploratory) return null;
  return (
    <span className={styles.root}>
      <StatusBadge tone={TONE[status]}>{words(status, sessions)}</StatusBadge>
    </span>
  );
}
