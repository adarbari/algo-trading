/**
 * Completeness of every dataset over the last ten sessions as a HeatGrid (complete / partial /
 * failed / not collected, each cell's share of expected rows). Selecting a cell drills in.
 */
import { EmptyState, ErrorState, HeatGrid, Panel, Skeleton } from '@algotrade/ui';

import {
  gridColumns,
  gridRows,
  SESSIONS,
  useCompleteness,
  useFocusCell,
  type CellRef,
} from '@/entities/ingestion';

export interface CompletenessPanelProps {
  /** The selected cell (else the latest session's worst cell is outlined). */
  selected?: CellRef | null;
  onSelect: (cell: CellRef) => void;
}

export function CompletenessPanel({ selected, onSelect }: CompletenessPanelProps) {
  const completeness = useCompleteness();
  const focus = useFocusCell(selected);
  const data = completeness.data;
  return (
    <Panel
      title={`Completeness · last ${String(SESSIONS)} sessions`}
      description="share of expected rows present"
      footer="Not collected: before a dataset's first stored session. Failed: missing after it was collected. Select a cell to drill in."
    >
      {completeness.isPending ? (
        <Skeleton variant="rect" height="lg" label="Loading completeness…" />
      ) : completeness.isError ? (
        <ErrorState
          compact
          title="Completeness could not load."
          detail={completeness.error.message}
          onRetry={() => void completeness.refetch()}
          retrying={completeness.isFetching}
        />
      ) : !data || data.cells.length === 0 ? (
        <EmptyState
          compact
          title="Nothing ingested yet"
          description="Run the nightly ingestion to fill the grid."
        />
      ) : (
        <HeatGrid
          label="Completeness by dataset and session"
          rowHeader="Dataset"
          rows={gridRows(data)}
          columns={gridColumns(data)}
          selected={focus ? { row: focus.dataset, column: focus.session } : null}
          onSelect={({ row, column }) => {
            onSelect({ dataset: row, session: column });
          }}
        />
      )}
    </Panel>
  );
}
