/**
 * A copy of an edge beside the edge it extends and the baselines: one row each, in-sample, and
 * out-of-sample only once the user has shown it (the server withholds it until then, and says
 * why a comparison is empty). Every figure and word is served.
 */
import { DataTable, Panel, Stack, Text } from '@algotrade/ui';
import { useMemo } from 'react';

import { useEdgeCompare, type CompareRow } from '@/features/edge-compare';
import { GuideHelp } from '@/features/guide-help';

import { compareColumns } from '../model/columns';

export interface EdgeCompareProps {
  /** The copy whose comparison is shown. */
  edgeId: string;
}

export function EdgeCompare({ edgeId }: EdgeCompareProps) {
  const found = useEdgeCompare(edgeId);
  const compare = found.data;
  const columns = useMemo(() => compareColumns(compare ? !compare.oosHidden : false), [compare]);
  return (
    <Panel
      title="Compare versions"
      flush
      state={found.isError ? 'error' : found.isPending ? 'loading' : 'ready'}
      loadingLabel="Loading comparison…"
      errorMessage="The comparison failed to load."
      onRetry={() => void found.refetch()}
      actions={<GuideHelp entry={{ kind: 'term', id: 'compare_versions' }} />}
    >
      <Stack gap={2}>
        {compare?.reason && (
          <Text size="sm" tone="muted">
            {compare.reason}
          </Text>
        )}
        {compare && compare.rows.length > 0 && (
          <DataTable<CompareRow>
            label="Compare versions"
            columns={columns}
            rows={compare.rows}
            getRowId={(r) => `${r.label}:${r.basis}`}
            emptyMessage="Nothing to compare yet"
            visibleRows={8}
          />
        )}
      </Stack>
    </Panel>
  );
}
