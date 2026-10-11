/**
 * The figures behind the verdict, one column per side of the split: in-sample, out-of-sample
 * (marked, and "n=" when the sample is thin) and all. A side the run did not store is absent and
 * a figure it did not store reads as missing. Every figure and flag is the verdict's `columns`.
 */
import { DataTable, Panel } from '@algotrade/ui';
import { useMemo } from 'react';

import type { EdgeVerdict } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { figureColumns, FIGURES } from '../model/figures';

export interface EdgeFiguresProps {
  verdict: EdgeVerdict;
}

export function EdgeFigures({ verdict }: EdgeFiguresProps) {
  const columns = useMemo(() => figureColumns(verdict.columns), [verdict.columns]);
  return (
    <Panel
      title="Figures"
      headingLevel={3}
      flush
      actions={termHelp('edge_figures')}
      state={verdict.columns.length === 0 ? 'empty' : 'ready'}
      emptyMessage="No figures yet: the edge has no official result"
    >
      <DataTable
        label="In-sample, out-of-sample and all figures"
        columns={columns}
        rows={FIGURES}
        getRowId={(row) => row.id}
        emptyMessage="No figures"
      />
    </Panel>
  );
}
