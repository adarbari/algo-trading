/**
 * The caller's regime rules, read-only: the size new positions get in each kind of weather, the
 * size when the weather is not computed, and for each of their screeners the labels it pauses
 * in (or that its gate is off). The values are the effective `[regime]` settings the server
 * resolved for the caller; they are edited in the config files, never here. Data, empty and
 * error states.
 */
import { KeyValue, Panel, Skeleton, Stack, Text } from '@algotrade/ui';

import { gatePauses, plainLabel, useRegime } from '@/entities/regime';

export interface RegimeSizingProps {
  /** The panel title (the page it sits on says whose rules these are). */
  title?: string;
}

export function RegimeSizing({ title = 'How the regime sizes your positions' }: RegimeSizingProps) {
  const regime = useRegime();
  const sizing = regime.data?.sizing;
  const state = regime.isError ? 'error' : regime.isPending || sizing ? 'ready' : 'empty';
  return (
    <Panel
      title={title}
      description="Read-only: set under [regime] in your config files"
      state={state}
      emptyMessage="No regime rules are stored yet."
      errorMessage="The regime rules failed to load."
      onRetry={() => void regime.refetch()}
    >
      {regime.isPending && <Skeleton lines={5} label="Loading the regime rules" />}
      {sizing ? (
        <Stack gap={3}>
          <Text size="sm" tone="secondary">
            {sizing.enabled
              ? 'The regime gate is on: new positions are sized by the weather and some screeners pause.'
              : 'The regime gate is off: new positions are at full size and nothing pauses.'}
          </Text>
          <KeyValue
            label="Size of a new position"
            items={[
              ...sizing.multipliers.map((m) => ({
                id: m.label,
                label: plainLabel(m.label),
                value: m.multiplier,
                format: { kind: 'percent' as const, digits: 0 },
              })),
              {
                id: 'unknown',
                label: 'Weather not computed',
                value: sizing.unknownMultiplier,
                format: { kind: 'percent' as const, digits: 0 },
                hint: 'Used when no regime is stored for the session',
              },
            ]}
            alignValues="end"
          />
          <KeyValue
            label="Your screeners"
            items={sizing.screeners.map((gate) => ({
              id: gate.screenerId,
              label: gate.name,
              value: gatePauses(gate),
            }))}
            alignValues="end"
          />
        </Stack>
      ) : null}
    </Panel>
  );
}
