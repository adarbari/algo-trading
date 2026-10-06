/**
 * The Builder's regime gate in one line under the draft bar: "This screen pauses in Storm and
 * Severe storm" or "No regime gate", read from the caller's served sizing rule, with a link to
 * the Regime page. Read-only: the gate is set in the user's config files (`[regime]`), not
 * here, and the muted note says so.
 */
import { Button, Skeleton, Stack, Text } from '@algotrade/ui';

import { gateLine, useRegime } from '@/entities/regime';

export interface RegimeGateLineProps {
  /** The screen being built (its config id). */
  screenerId: string;
  /** Open the Regime page. */
  onOpenRegime: () => void;
}

export function RegimeGateLine({ screenerId, onOpenRegime }: RegimeGateLineProps) {
  const regime = useRegime();
  if (regime.isPending) return <Skeleton lines={1} label="Reading the regime gate" />;
  const sizing = regime.data?.sizing;
  const line = regime.isError
    ? 'The regime gate could not be read.'
    : sizing
      ? gateLine(sizing, screenerId)
      : 'No regime gate';
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      <Text size="sm">{line}</Text>
      <Button size="sm" variant="ghost" onClick={onOpenRegime}>
        See the Regime page
      </Button>
      <Text size="xs" tone="muted">
        Set in your config files under [regime]; not editable here.
      </Text>
    </Stack>
  );
}
