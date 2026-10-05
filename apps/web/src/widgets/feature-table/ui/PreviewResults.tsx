/**
 * The Builder's preview (latest closed session): decision counts in the title, decision filter
 * chips, and the top rows in the same table as a stored run's results (rank, ticker, decision,
 * score with how it was worked out, each criterion tinted when missed, the screen's own
 * columns), sorted in the table. Enter on a row opens the ticker in Explore.
 */
import { Chip, Stack } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { previewPanelState, useScreenerBuilder } from '@/features/screener-builder';
import { byName, featureLabel, useFeatureCatalogue } from '@/entities/feature';
import { DEFAULT_DECISIONS, decisionCounts, decisionLabel } from '@/entities/screen';

import { resultsPlan } from '../model/plan';
import { previewRows } from '../model/rows';

import { TableFrame } from './TableFrame';

export interface PreviewResultsProps {
  /** Open a ticker in Explore. */
  onOpen: (symbol: string) => void;
}

const count = (n: number) => n.toLocaleString('en-US');

export function PreviewResults({ onOpen }: PreviewResultsProps) {
  const { preview } = useScreenerBuilder();
  const [decisions, setDecisions] = useState<string[]>([]);
  const data = preview.data;
  const catalogue = useFeatureCatalogue();
  const known = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const rows = useMemo(
    () =>
      previewRows(
        (data?.rows ?? []).filter((r) => decisions.length === 0 || decisions.includes(r.decision)),
      ),
    [data, decisions],
  );
  const plan = useMemo(
    () =>
      resultsPlan({
        criteria: data?.criteria ?? [],
        displayColumns: data?.display_columns ?? [],
        added: [],
        catalogue: known,
        labelOf: (id, field) => {
          const info = known.get(field);
          return info ? featureLabel(info.name) : decisionLabel(id);
        },
      }),
    [data, known],
  );
  const counts = data ? decisionCounts(data) : [];
  const title = counts.length
    ? `Preview · ${counts
        .filter((c) => DEFAULT_DECISIONS.includes(c.decision))
        .map((c) => `${count(c.count)} ${decisionLabel(c.decision).toLowerCase()}`)
        .join(' · ')}`
    : 'Preview';
  return (
    <TableFrame
      panel={{
        title,
        description: data
          ? `Top ${String(data.rows.length)} of ${count(data.total)} on ${data.session}`
          : undefined,
        state: previewPanelState(preview),
        loadingLabel: 'Running the preview…',
        emptyMessage: 'Add a complete criterion to preview what it would pick.',
        errorMessage: preview.error ?? 'The preview failed.',
        actions: (
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
        ),
        footer: 'Score is for sorting only; ties sort by the tie-break column.',
      }}
      summary={data ? `${count(rows.length)} shown` : 'Running the preview…'}
      grid={{
        label: 'Preview results',
        columns: plan,
        rows,
        getRowId: (row) => row.instrumentId,
        defaultSort: { columnId: 'rank', direction: 'asc' },
        sortMode: 'client',
        onRowActivate: (row) => {
          onOpen(row.symbol);
        },
        emptyMessage: 'No row has this decision.',
        visibleRows: 12,
        columnPicker: true,
      }}
    />
  );
}
