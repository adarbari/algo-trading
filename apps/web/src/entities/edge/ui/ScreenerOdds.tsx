/**
 * A screener's odds line (Ideas): its frozen-period record from the first edge that has a run,
 * at the shortest horizon, through `OddsLine`; why there is none when no edge ran (the server's
 * words); nothing when no edge lists the screener. Never an exploratory figure.
 */
import { OddsLine } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { unknownText } from '@/entities/availability';

import { useTrackRecords } from '../api/track-records';
import { oddsEntry } from '../model/track-records';
import { StoredOdds } from './StoredOdds';

export interface ScreenerOddsProps {
  screenerId: string;
  /** The Guide button for the line (the widget supplies it). */
  info?: ReactNode;
}

export function ScreenerOdds({ screenerId, info }: ScreenerOddsProps) {
  const records = useTrackRecords(screenerId);
  if (records.isPending) return <OddsLine state="loading" />;
  if (records.isError) return <OddsLine state="error" />;
  const entries = records.data;
  const entry = oddsEntry(entries);
  if (entries.length === 0) return null;
  const horizon = entry?.horizons[0];
  if (!entry || !horizon) {
    return (
      <OddsLine
        state="empty"
        message={unknownText(entries[0]?.notRun)}
        {...(info ? { info } : {})}
      />
    );
  }
  return (
    <StoredOdds
      hitRate={horizon.hitRate ?? null}
      baseRate={horizon.baseRate ?? null}
      sessions={horizon.sessions ?? null}
      liftPts={horizon.liftPts}
      picks={horizon.picks}
      runLabel={entry.runLabel}
      info={info}
    />
  );
}
