/**
 * Drawdown: how far the evidence curve fell below its previous high (an underwater chart of the
 * windows, by the session each was known), the deepest drops with their dates, and the deepest
 * drop and volatility of each side of the split (its own read, `edgeResult.drawdown`, fetched
 * when this view opens). An outcome with no return has none: the server says why. States:
 * loading, error, unknown, ready.
 */
import {
  Chart,
  DataTable,
  ErrorState,
  Skeleton,
  Stack,
  StatStrip,
  type StatItem,
} from '@algotrade/ui';

import { UnknownNote } from '@/entities/availability';
import { useEdgeDrawdown, type DrawdownEpisode } from '@/entities/edge';

import { episodeColumns } from '../model/columns';

const PERCENT = { kind: 'percent', digits: 1 } as const;

export interface EdgeDrawdownProps {
  edgeId: string;
}

export function EdgeDrawdown({ edgeId }: EdgeDrawdownProps) {
  const query = useEdgeDrawdown(edgeId);
  const drawdown = query.data;
  if (query.isPending) return <Skeleton variant="rect" label="Loading the drawdown" />;
  if (query.isError || !drawdown) {
    return (
      <ErrorState
        compact
        title="The drawdown failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (drawdown.unknown) return <UnknownNote unknown={drawdown.unknown} />;
  const stats: StatItem[] = [
    {
      id: 'max-is',
      label: 'Deepest drop · in-sample',
      value: drawdown.maxInSample,
      format: PERCENT,
    },
    {
      id: 'max-oos',
      label: 'Deepest drop · out-of-sample',
      value: drawdown.maxOutOfSample,
      format: PERCENT,
    },
    { id: 'vol-is', label: 'Volatility · in-sample', value: drawdown.volInSample, format: PERCENT },
    {
      id: 'vol-oos',
      label: 'Volatility · out-of-sample',
      value: drawdown.volOutOfSample,
      format: PERCENT,
    },
  ];
  return (
    <Stack gap={3}>
      <Chart
        label="Evidence curve below its previous high"
        series={[
          {
            id: 'underwater',
            label: 'Below the high',
            type: 'underwater',
            points: drawdown.points.map((p) => ({ time: p.exit, value: p.depth })),
          },
        ]}
        format={{ kind: 'delta', unit: 'percent', digits: 1 }}
        emptyMessage="No windows to draw"
      />
      <StatStrip label="Drawdown and volatility" items={stats} />
      <DataTable<DrawdownEpisode>
        label="Deepest drawdowns"
        columns={episodeColumns}
        rows={drawdown.episodes}
        getRowId={(e) => `${e.peak}:${e.trough}`}
        emptyMessage="No drawdowns"
      />
    </Stack>
  );
}
