/**
 * The latest calls, newest first, with every column of the usage log; choosing a row opens that
 * call's detail beside the table (the page's MasterDetail; the choice lives in the URL).
 */
import { DataTable } from '@algotrade/ui';

import { callId, UsagePanel } from '@/entities/llm-usage';

import { CALL_COLUMNS } from '../model/columns';

export interface UsageCallsPanelProps {
  /** The chosen call (its `callId`), if any. */
  selected: string | null;
  onSelect: (id: string) => void;
}

export function UsageCallsPanel({ selected, onSelect }: UsageCallsPanelProps) {
  return (
    <UsagePanel title="Recent calls" description="newest first; select one for its detail" flush>
      {(usage) => (
        <DataTable
          label="Recent text-model calls"
          columns={CALL_COLUMNS}
          rows={usage.recent}
          getRowId={callId}
          activeRowId={selected}
          onRowActivate={(call) => {
            onSelect(callId(call));
          }}
          sortMode="client"
          visibleRows={Math.min(usage.recent.length, 12)}
        />
      )}
    </UsagePanel>
  );
}
