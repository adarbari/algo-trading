/**
 * Capacity: how much money the picks can take, for one period (an In-sample / Out-of-sample / All
 * switch): the site's floor, the median 20-day dollar volume of the counted picks and how many
 * trade below the floor. Its own read (`edgeResult.capacity`). A period not measured says so in
 * words. States: loading, error, not measured, ready.
 */
import {
  ErrorState,
  formatValue,
  KeyValue,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  type KeyValueItem,
  type SegmentedOption,
} from '@algotrade/ui';
import { useState } from 'react';

import { sliceStateLabel, useEdgeCapacity } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

type View = 'in_sample' | 'out_of_sample' | 'all';

const OPTIONS: SegmentedOption<View>[] = [
  { value: 'in_sample', label: 'In-sample' },
  { value: 'out_of_sample', label: 'Out-of-sample' },
  { value: 'all', label: 'All' },
];

export interface EdgeCapacityProps {
  edgeId: string;
}

export function EdgeCapacity({ edgeId }: EdgeCapacityProps) {
  const query = useEdgeCapacity(edgeId);
  const [view, setView] = useState<View>('out_of_sample');
  const capacity = query.data;
  if (query.isPending) return <Skeleton variant="rect" label="Loading the capacity" />;
  if (query.isError || !capacity) {
    return (
      <ErrorState
        compact
        title="The capacity failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  const period = capacity.periods.find((p) => p.period === view);
  // The site floor says something only when it is above the floor the universe already has.
  const items: KeyValueItem[] = capacity.floorBinds
    ? [
        {
          id: 'floor',
          label: 'Universe floor, 20-day dollar volume',
          value: capacity.floorUsd,
          format: { kind: 'currency-compact' },
        },
      ]
    : [];
  if (period?.state === 'measured') {
    items.push(
      { id: 'picks', label: 'Picks counted', value: period.picks, format: { kind: 'number' } },
      {
        id: 'median',
        label: 'Median pick, 20-day dollar volume',
        value: period.advMedian,
        format: { kind: 'currency-compact' },
      },
      {
        id: 'known',
        label: 'Picks with a stored volume',
        value: period.advKnown,
        format: { kind: 'number' },
      },
      ...(capacity.floorBinds
        ? [
            {
              id: 'low',
              label: 'Picks under the floor',
              value: period.advLow,
              format: { kind: 'number' as const },
            },
          ]
        : []),
      {
        id: 'position',
        label: `${formatValue(capacity.positionUsd, { kind: 'currency-compact' }).text} position, share of the median pick's volume`,
        value: period.positionShare,
        format: { kind: 'percent', digits: 2 },
      },
    );
  }
  return (
    <Stack gap={2}>
      <SegmentedControl
        aria-label="Period of the capacity"
        size="sm"
        options={OPTIONS}
        value={view}
        onValueChange={setView}
      />
      {capacity.state !== 'measured' || (period && period.state !== 'measured') ? (
        <Stack direction="row" gap={1} align="center">
          <Text tone="secondary">
            {sliceStateLabel(
              period && capacity.state === 'measured' ? period.state : capacity.state,
            )}
          </Text>
          {termHelp('cost_state')}
        </Stack>
      ) : null}
      <KeyValue label="Capacity" items={items} />
    </Stack>
  );
}
