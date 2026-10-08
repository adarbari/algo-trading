/**
 * An `OddsLine` for figures as the server stored them: hit rate, base rate and sessions are
 * needed together (a bare hit rate is never shown), so a partial row reads as "not stored".
 * Only frozen-period figures reach it: the caller never passes an exploratory run's.
 */
import { OddsLine } from '@algotrade/ui';
import type { ReactNode } from 'react';

export interface StoredOddsProps {
  hitRate: number | null;
  baseRate: number | null;
  sessions: number | null;
  lift?: number | null;
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
  lift,
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
      {...(lift == null ? {} : { lift })}
      {...(picks == null ? {} : { picks })}
      {...(runLabel ? { runLabel } : {})}
      {...(info ? { info } : {})}
    />
  );
}
