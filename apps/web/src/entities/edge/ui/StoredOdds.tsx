/**
 * An `OddsLine` for figures as the server stored them: win rate, base rate and trades are
 * needed together (a bare win rate is never shown), so a partial row reads as "not stored".
 * Only frozen-period figures reach it: the caller never passes an exploratory run's.
 */
import { OddsLine } from '@algotrade/ui';
import type { ReactNode } from 'react';

export interface StoredOddsProps {
  hitRate: number | null;
  baseRate: number | null;
  sessions: number | null;
  liftPts?: number | null;
  picks?: number | null;
  /** The run the figures come from. */
  runLabel?: string | null;
  /** The Guide button for the line (the widget supplies it). */
  info?: ReactNode;
}

export function StoredOdds({
  hitRate,
  baseRate,
  sessions,
  liftPts,
  picks,
  runLabel,
  info,
}: StoredOddsProps) {
  if (hitRate === null || baseRate === null || sessions === null) {
    return <OddsLine state="empty" message="Not stored" {...(info ? { info } : {})} />;
  }
  return (
    <OddsLine
      hitRate={hitRate}
      baseRate={baseRate}
      sessions={sessions}
      {...(liftPts == null ? {} : { liftPts })}
      {...(picks == null ? {} : { picks })}
      {...(runLabel ? { runLabel } : {})}
      {...(info ? { info } : {})}
    />
  );
}
