/**
 * The latest calls, newest first, with every column of the usage log; choosing a row opens that
 * call's detail beside the table (the page's MasterDetail; the choice lives in the URL). The
 * "Failures" view lists only the calls that failed (a provider that raised) or were rejected (an
 * answer the caller could not use), whose detail holds the message, the prompt and the raw answer.
 */
import { DataTable, SegmentedControl } from '@algotrade/ui';
import { useState } from 'react';

import { callId, TERM_OF_REJECTED, UsagePanel } from '@/entities/llm-usage';
import { termHelp } from '@/features/guide-help';

import { CALL_COLUMNS } from '../model/columns';

export interface UsageCallsPanelProps {
  /** The chosen call (its `callId`), if any. */
  selected: string | null;
  onSelect: (id: string) => void;
}

type View = 'all' | 'failures';

export function UsageCallsPanel({ selected, onSelect }: UsageCallsPanelProps) {
  const [view, setView] = useState<View>('all');
  return (
    <UsagePanel
      title={view === 'all' ? 'Recent calls' : 'Failed and rejected calls'}
      description="newest first; select one for its detail"
      actions={
        <>
          <SegmentedControl<View>
            aria-label="Which calls"
            size="sm"
            value={view}
            onValueChange={setView}
            options={[
              { value: 'all', label: 'All calls' },
              { value: 'failures', label: 'Failures' },
            ]}
          />
          {termHelp(TERM_OF_REJECTED)}
        </>
      }
      flush
    >
      {(usage) => {
        const rows = view === 'all' ? usage.recent : usage.failures;
        return (
          <DataTable
            label={view === 'all' ? 'Recent text-model calls' : 'Failed text-model calls'}
            columns={CALL_COLUMNS}
            rows={rows}
            getRowId={callId}
            activeRowId={selected}
            onRowActivate={(call) => {
              onSelect(callId(call));
            }}
            sortMode="client"
            visibleRows={Math.min(rows.length, 12)}
          />
        );
      }}
    </UsagePanel>
  );
}
