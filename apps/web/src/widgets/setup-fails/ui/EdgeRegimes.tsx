/**
 * Where it worked, by regime: the verdict's basis in each market regime (calm, caution, stress,
 * crisis) with the win rate, base rate, lift and trades of one period (an In-sample /
 * Out-of-sample / All switch). Its own read (`edgeResult.regimes`), fetched when the view opens.
 * A regime figure the harness did not store, or a copy hides, says so in words. States: loading,
 * error, ready (a section-level state other than measured is said once, above the table).
 */
import {
  DataTable,
  ErrorState,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  type SegmentedOption,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { sliceStateLabel, useEdgeRegimes } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { regimeColumns, regimeViews, type RegimeView } from '../model/slice-columns';

type View = 'in_sample' | 'out_of_sample' | 'all';

const OPTIONS: SegmentedOption<View>[] = [
  { value: 'in_sample', label: 'In-sample' },
  { value: 'out_of_sample', label: 'Out-of-sample' },
  { value: 'all', label: 'All' },
];

export interface EdgeRegimesProps {
  edgeId: string;
}

export function EdgeRegimes({ edgeId }: EdgeRegimesProps) {
  const query = useEdgeRegimes(edgeId);
  const [view, setView] = useState<View>('all');
  const regimes = query.data;
  const rows = useMemo(() => regimeViews(regimes?.rows ?? [], view), [regimes, view]);
  if (query.isPending) return <Skeleton variant="rect" label="Loading the regimes" />;
  if (query.isError || !regimes) {
    return (
      <ErrorState
        compact
        title="The regimes failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center" wrap>
        <SegmentedControl
          aria-label="Period shown"
          size="sm"
          options={OPTIONS}
          value={view}
          onValueChange={setView}
        />
        <Text tone="muted" size="sm">
          Regime at the decision session
        </Text>
        {termHelp('by_regime')}
      </Stack>
      {regimes.state !== 'measured' && (
        <Stack direction="row" gap={1} align="center">
          <Text tone="secondary">{sliceStateLabel(regimes.state)}</Text>
          {termHelp('slice_state')}
        </Stack>
      )}
      <DataTable<RegimeView>
        label="By regime"
        columns={regimeColumns}
        rows={rows}
        getRowId={(r) => r.regime}
        emptyMessage="No regime has trades"
        visibleRows={8}
      />
    </Stack>
  );
}
