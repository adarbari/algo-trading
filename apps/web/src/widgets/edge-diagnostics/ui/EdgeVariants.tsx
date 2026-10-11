/**
 * Variants tried: the grid of every screen and holding period the official run measured (its own
 * read, `edgeVariants`), the lift of each period with its trades. The verdict's basis is marked,
 * every other row's out-of-sample figure says it is not the pre-chosen test, and a copy's hidden
 * out-of-sample result is said once. States: loading, error, unknown (why there is no grid), ready.
 */
import { DataTable, ErrorState, Skeleton, Stack, Text } from '@algotrade/ui';

import { UnknownNote } from '@/entities/availability';
import { EDGE_UNKNOWN_WORDS, useEdgeVariants, type EdgeVariant } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { variantColumns } from '../model/variant-columns';

export interface EdgeVariantsProps {
  edgeId: string;
}

export function EdgeVariants({ edgeId }: EdgeVariantsProps) {
  const query = useEdgeVariants(edgeId);
  const grid = query.data;
  if (query.isPending) return <Skeleton variant="rect" label="Loading the variants" />;
  if (query.isError || !grid) {
    return (
      <ErrorState
        compact
        title="The variants failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (grid.unknown) return <UnknownNote unknown={grid.unknown} kindWords={EDGE_UNKNOWN_WORDS} />;
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center" wrap>
        <Text tone="muted" size="sm">
          Lift, pts (trades)
        </Text>
        {grid.trials != null && (
          <Text tone="muted" size="sm">{`${String(grid.trials)} variants tried`}</Text>
        )}
        {grid.oosHidden && (
          <>
            <Text tone="secondary">Out-of-sample hidden</Text>
            {termHelp('show_out_of_sample')}
          </>
        )}
      </Stack>
      <DataTable<EdgeVariant>
        label="Variant grid: lift in points by holding period"
        columns={variantColumns}
        rows={grid.rows}
        getRowId={(r) => `${r.edgeVariant}:${r.variant}:${String(r.horizonSessions)}`}
        emptyMessage="No variants measured"
        visibleRows={10}
      />
    </Stack>
  );
}
