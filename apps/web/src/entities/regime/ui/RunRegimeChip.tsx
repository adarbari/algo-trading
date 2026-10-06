/**
 * The regime a screener run stamped on its rows (the session's label when it ran), as a chip in
 * the results header: the weather word in its tone. A run with no stamp (the gate was off, the
 * label unknown, or the run came before the stamp) says so in a muted chip, never nothing.
 */
import { StatusBadge } from '@algotrade/ui';

import { plainLabel, regimeTone, storedLabel } from '../model/regime';

export interface RunRegimeChipProps {
  /** The run's stored label (`ScreenerRun.regime`), null when it has none. */
  label: string | null | undefined;
}

export function RunRegimeChip({ label }: RunRegimeChipProps) {
  const known = storedLabel(label);
  if (known === null) {
    return (
      <StatusBadge
        tone="neutral"
        title="The gate was off for this run, the market regime was not computed, or the run came before regime stamps"
      >
        Regime: not recorded for this run
      </StatusBadge>
    );
  }
  return (
    <StatusBadge tone={regimeTone(known)} title="The market regime when this run was made">
      {`Regime: ${plainLabel(known)}`}
    </StatusBadge>
  );
}
