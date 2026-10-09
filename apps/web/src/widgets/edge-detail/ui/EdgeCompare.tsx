/**
 * A copy of an edge beside the edge it extends and the baselines: one row each, in-sample, and
 * out-of-sample only once the user has shown it (the server withholds it until then, and says
 * why a comparison is empty). Every figure and word is served.
 */
import { DataTable, Panel, Stack, Text } from '@algotrade/ui';
import { useMemo } from 'react';

import type { CompareRow, EdgeCompare as Compare } from '@/entities/edge';
import { GuideHelp } from '@/features/guide-help';

import { compareColumns } from '../model/columns';

export interface EdgeCompareProps {
  compare: Compare;
}

export function EdgeCompare({ compare }: EdgeCompareProps) {
  const columns = useMemo(() => compareColumns(!compare.oosHidden), [compare.oosHidden]);
  return (
    <Panel
      title="Compare versions"
      flush
      actions={<GuideHelp entry={{ kind: 'term', id: 'compare_versions' }} />}
    >
      <Stack gap={2}>
        {compare.reason && (
          <Text size="sm" tone="muted">
            {compare.reason}
          </Text>
        )}
        {compare.rows.length > 0 && (
          <DataTable<CompareRow>
            label="Compare versions"
            columns={columns}
            rows={compare.rows}
            getRowId={(r) => `${r.kind}:${r.label}:${r.basis}`}
            emptyMessage="Nothing to compare yet"
            visibleRows={8}
          />
        )}
      </Stack>
    </Panel>
  );
}
