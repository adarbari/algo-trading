/**
 * The cost strip under Where it worked: the lift at each round-trip cost the harness measured
 * (the document's own cost marked) for one period, and the cost at which the mean excess return
 * reaches zero (the break-even). Its own read (`edgeResult.costs`). An outcome that is not a
 * return has no cost rows (NOT_A_COST_OUTCOME): the strip says so instead of drawing one.
 * States: loading, error, not measured (a word and its Guide entry), ready.
 */
import {
  ErrorState,
  SegmentedControl,
  Skeleton,
  Stack,
  StatStrip,
  Text,
  type SegmentedOption,
  type StatItem,
} from '@algotrade/ui';
import { useState } from 'react';

import { sliceStateLabel, useEdgeCosts } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

type View = 'in_sample' | 'out_of_sample' | 'all';

const OPTIONS: SegmentedOption<View>[] = [
  { value: 'in_sample', label: 'In-sample' },
  { value: 'out_of_sample', label: 'Out-of-sample' },
  { value: 'all', label: 'All' },
];

export interface EdgeCostsProps {
  edgeId: string;
}

export function EdgeCosts({ edgeId }: EdgeCostsProps) {
  const query = useEdgeCosts(edgeId);
  const [view, setView] = useState<View>('out_of_sample');
  const costs = query.data;
  if (query.isPending) return <Skeleton variant="rect" label="Loading the costs" />;
  if (query.isError || !costs) {
    return (
      <ErrorState compact title="The costs failed to load." onRetry={() => void query.refetch()} />
    );
  }
  const head = (
    <Stack direction="row" gap={1} align="center" wrap>
      <Text weight="medium">Cost sensitivity</Text>
      {termHelp('cost_sensitivity')}
    </Stack>
  );
  if (costs.state !== 'measured') {
    return (
      <Stack gap={1}>
        {head}
        <Stack direction="row" gap={1} align="center">
          <Text tone="secondary">{sliceStateLabel(costs.state)}</Text>
          {termHelp('cost_state')}
        </Stack>
      </Stack>
    );
  }
  const period = costs.periods.find((p) => p.period === view);
  const items: StatItem[] = costs.levels
    .filter((l) => l.period === view)
    .map((l) => ({
      id: String(l.bp),
      label: l.assumed ? `${String(l.bp)} bp · the edge's cost` : `${String(l.bp)} bp`,
      value: l.liftPts,
      format: { kind: 'delta', unit: 'points', digits: 1 },
    }));
  if (period?.breakEvenBp != null) {
    items.push({
      id: 'break-even',
      label: 'Break-even, bp',
      value: period.breakEvenBp,
      format: { kind: 'number', digits: 0 },
    });
  }
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={2} align="center" wrap>
        {head}
        <SegmentedControl
          aria-label="Period of the costs"
          size="sm"
          options={OPTIONS}
          value={view}
          onValueChange={setView}
        />
      </Stack>
      {period && period.state !== 'measured' ? (
        <Stack direction="row" gap={1} align="center">
          <Text tone="secondary">{sliceStateLabel(period.state)}</Text>
          {termHelp('cost_state')}
        </Stack>
      ) : (
        <StatStrip label="Lift at each round-trip cost" items={items} emptyMessage="No costs" />
      )}
    </Stack>
  );
}
