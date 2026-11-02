/**
 * Where it worked, by holding period: the verdict's screen at every holding period the run
 * measured, the lift (and trades) in-sample, out-of-sample and over the whole history, the row the
 * verdict rests on marked, every other row's out-of-sample figure labelled as not the pre-chosen
 * test, and the date the out-of-sample trades are expected to reach the count the verdict needs.
 * Its own read (`edgeResult.horizons`), fetched when the view opens.
 */
import { DataTable, ErrorState, Skeleton, Stack, Text } from '@algotrade/ui';
import { useMemo } from 'react';

import { sliceStateLabel, useEdgeHorizons, type HorizonRow } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { horizonColumns } from '../model/slice-columns';

export interface EdgeHorizonsProps {
  edgeId: string;
}

export function EdgeHorizons({ edgeId }: EdgeHorizonsProps) {
  const query = useEdgeHorizons(edgeId);
  const horizons = query.data;
  const columns = useMemo(() => horizonColumns(horizons?.needed ?? 0), [horizons?.needed]);
  if (query.isPending) return <Skeleton variant="rect" label="Loading the holding periods" />;
  if (query.isError || !horizons) {
    return (
      <ErrorState
        compact
        title="The holding periods failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center" wrap>
        <Text tone="muted" size="sm">
          Lift, pts (trades)
        </Text>
        {termHelp('by_holding_period')}
        {horizons.state !== 'measured' && (
          <>
            <Text tone="secondary">{sliceStateLabel(horizons.state)}</Text>
            {termHelp('slice_state')}
          </>
        )}
      </Stack>
      <DataTable<HorizonRow>
        label="By holding period"
        columns={columns}
        rows={horizons.rows}
        getRowId={(r) => String(r.horizon)}
        emptyMessage="No holding period measured"
        visibleRows={8}
      />
    </Stack>
  );
}
