/**
 * The regime as a chip beside the session date: the weather word in its tone, the headline
 * sentence on hover, a click opens the Regime page. UNKNOWN shows "Regime: not computed" in a
 * muted tone, never hidden; a failed read says so. One chip for every embedding (ADR 0047).
 */
import { Button, Skeleton, StatusBadge } from '@algotrade/ui';

import { useRegime } from '../api/hooks';
import { plainLabel, regimeTone } from '../model/regime';

export interface RegimeChipProps {
  /** Open the Regime page. */
  onOpen: () => void;
}

export function RegimeChip({ onOpen }: RegimeChipProps) {
  const regime = useRegime();
  if (regime.isPending) return <Skeleton lines={1} label="Loading the market regime" />;
  const data = regime.data;
  const unknown = data?.label === 'UNKNOWN';
  const text = regime.isError
    ? 'Regime: unavailable'
    : data === null || data === undefined || unknown
      ? 'Regime: not computed'
      : `Regime: ${plainLabel(data.label)}`;
  const title = data ? data.headline : 'The market regime could not be read.';
  return (
    <Button variant="ghost" size="sm" onClick={onOpen}>
      <StatusBadge tone={data ? regimeTone(data.label) : 'neutral'} title={title}>
        {text}
      </StatusBadge>
    </Button>
  );
}
