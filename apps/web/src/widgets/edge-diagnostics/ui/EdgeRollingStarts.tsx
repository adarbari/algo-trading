/**
 * Rolling starts: the lift you would have seen starting at the beginning of each year and holding
 * every window after it, one line (its own read, `edgeResult.rollingStarts`). An outcome with no
 * such figure says why. States: loading, error, unknown, ready.
 */
import { Chart, ErrorState, Skeleton } from '@algotrade/ui';

import { UnknownNote } from '@/entities/availability';
import { EDGE_UNKNOWN_WORDS, useEdgeRollingStarts } from '@/entities/edge';

export interface EdgeRollingStartsProps {
  edgeId: string;
}

export function EdgeRollingStarts({ edgeId }: EdgeRollingStartsProps) {
  const query = useEdgeRollingStarts(edgeId);
  const rolling = query.data;
  if (query.isPending) return <Skeleton variant="rect" label="Loading the rolling starts" />;
  if (query.isError || !rolling) {
    return (
      <ErrorState
        compact
        title="The rolling starts failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (rolling.unknown)
    return <UnknownNote unknown={rolling.unknown} kindWords={EDGE_UNKNOWN_WORDS} />;
  return (
    <Chart
      label="Lift measured from each start to today"
      series={[
        {
          id: 'rolling',
          label: 'Lift from the start',
          points: rolling.starts.flatMap((s) =>
            s.liftPts == null ? [] : [{ time: s.start, value: s.liftPts }],
          ),
        },
      ]}
      format={{ kind: 'delta', unit: 'points', digits: 1 }}
      emptyMessage="No starts to draw"
    />
  );
}
