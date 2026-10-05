/**
 * The preview's top rows (latest closed session): decision counts in the title, decision filter
 * chips, score, each criterion (tinted when missed) and the screen's own columns. Click a row to open the ticker in Explore.
 */
import { Chip, DataTable, Panel, Stack } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { byName, useFeatureCatalogue } from '@/entities/feature';
import { decisionCounts, decisionLabel, extraColumns, type PreviewRow } from '@/entities/screen';
import { previewPanelState, useScreenerBuilder } from '@/features/screener-builder';

import { criterionColumns, previewColumns } from '../model/columns';

export interface PreviewResultsProps {
  /** Open a ticker in Explore. */
  onOpen: (symbol: string) => void;
}

export function PreviewResults({ onOpen }: PreviewResultsProps) {
  const { preview } = useScreenerBuilder();
  const [decisions, setDecisions] = useState<string[]>([]);
  const data = preview.data;
  const rows = useMemo(
    () =>
      (data?.rows ?? []).filter((r) => decisions.length === 0 || decisions.includes(r.decision)),
    [data, decisions],
  );
  const catalogue = useFeatureCatalogue();
  const known = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const columns = useMemo(
    () => previewColumns(criterionColumns(data?.rows ?? []), extraColumns(data?.rows ?? []), known),
    [data, known],
  );
  const counts = data ? decisionCounts(data) : [];
  const title = counts.length
    ? `Preview · ${counts
        .filter((c) => c.decision !== 'SKIPPED' && c.decision !== 'REJECT')
        .map((c) => `${c.count.toLocaleString('en-US')} ${decisionLabel(c.decision).toLowerCase()}`)
        .join(' · ')}`
    : 'Preview';
  return (
    <Panel
      title={title}
      description={
        data
          ? `Top ${String(data.rows.length)} of ${data.total.toLocaleString('en-US')} on ${data.session}`
          : undefined
      }
      flush
      state={previewPanelState(preview)}
      loadingLabel="Running the preview…"
      emptyMessage="Add a complete criterion to preview what it would pick."
      errorMessage={preview.error ?? 'The preview failed.'}
      actions={
        <Stack direction="row" gap={2} wrap>
          {counts.map(({ decision }) => (
            <Chip
              key={decision}
              label={decisionLabel(decision)}
              selected={decisions.includes(decision)}
              onSelectedChange={(on) => {
                setDecisions((d) => (on ? [...d, decision] : d.filter((x) => x !== decision)));
              }}
            />
          ))}
        </Stack>
      }
      footer="Score is for sorting only; ties sort by the tie-break column."
    >
      <DataTable<PreviewRow>
        label="Preview results"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.instrument_id}
        getRowLabel={(row) => row.symbol ?? row.instrument_id}
        defaultSort={{ columnId: 'rank', direction: 'asc' }}
        onRowActivate={(row) => {
          if (row.symbol) onOpen(row.symbol);
        }}
        emptyMessage="No row has this decision."
        visibleRows={12}
        columnPicker
      />
    </Panel>
  );
}
