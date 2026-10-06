/**
 * The regime strip at the top of Ideas: the chip, the headline sentence and the sizing rule in
 * force for new positions ("New positions sized at 100% (regime not computed)" until the
 * regime exists). Never hidden: not computed and a failed read say so.
 */
import { Stack, Text } from '@algotrade/ui';

import { RegimeChip, sizingLine, useRegime } from '@/entities/regime';

export interface RegimeStripProps {
  /** Open the Regime page. */
  onOpen: () => void;
}

// TODO(RG5): the "Paused by regime (n)" section (ideas the regime gate skipped, with their
// reasons) goes under this strip once the read model has the PAUSED decision (ADR 0049).
export function RegimeStrip({ onOpen }: RegimeStripProps) {
  const regime = useRegime();
  const data = regime.data;
  const sentence = regime.isError
    ? 'The market regime could not be read.'
    : (data?.headline ??
      (regime.isPending ? 'Reading the market regime…' : 'No regime is stored yet.'));
  const sizing = data ? sizingLine(data) : 'New positions sized at 100% (regime not computed)';
  return (
    <Stack direction="row" gap={3} align="center" wrap>
      <RegimeChip onOpen={onOpen} />
      <Text size="sm" tone="secondary">
        {sentence}
      </Text>
      <Text size="sm" tone="muted">
        {sizing}
      </Text>
    </Stack>
  );
}
