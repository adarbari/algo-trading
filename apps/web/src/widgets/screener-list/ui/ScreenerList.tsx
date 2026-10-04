/**
 * The screeners: the user's own (open to edit) and the site presets (view, or "Copy to my
 * screeners", which pins the preset's version). Python screeners are listed but built in code.
 */
import { DataTable, Panel, Stack } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { useScreeners, type ScreenerSummary } from '@/entities/screen';
import { CopyPresetDialog } from '@/features/screener-copy';

import { screenerColumns } from '../model/columns';

export interface ScreenerListProps {
  /** Open a screener in the Builder. */
  onOpen: (id: string) => void;
}

export function ScreenerList({ onOpen }: ScreenerListProps) {
  const screeners = useScreeners();
  const [copying, setCopying] = useState<string | null>(null);
  const columns = useMemo(() => screenerColumns({ onOpen, onCopy: setCopying }), [onOpen]);
  const all = screeners.data ?? [];
  const mine = all.filter((s) => s.scope !== 'site');
  const presets = all.filter((s) => s.scope === 'site');
  const state =
    screeners.isError && !screeners.data ? 'error' : screeners.isPending ? 'loading' : 'ready';
  const table = (label: string, rows: ScreenerSummary[], empty: string) => (
    <DataTable<ScreenerSummary>
      label={label}
      columns={columns}
      rows={rows}
      getRowId={(s) => `${s.scope}/${s.config_id}`}
      getRowLabel={(s) => s.config_id}
      defaultSort={{ columnId: 'name', direction: 'asc' }}
      emptyMessage={empty}
    />
  );
  return (
    <Stack gap={4}>
      <Panel
        title="Your screeners"
        description="Finalized screeners; a draft appears here once it is finalized"
        flush
        state={state}
        loadingLabel="Loading screeners…"
        errorMessage="The screeners failed to load."
        onRetry={() => void screeners.refetch()}
      >
        {table(
          'Your screeners',
          mine,
          'You have no finalized screener yet. Create one, or copy a preset.',
        )}
      </Panel>
      <Panel
        title="Site presets"
        description="Changed by pull request; copy one to make it yours"
        flush
        state={state}
        loadingLabel="Loading presets…"
        errorMessage="The presets failed to load."
      >
        {table('Site presets', presets, 'No site screener presets.')}
      </Panel>
      {copying && (
        <CopyPresetDialog
          preset={copying}
          open
          onOpenChange={(open) => {
            if (!open) setCopying(null);
          }}
          onCopied={(id) => {
            setCopying(null);
            onOpen(id);
          }}
        />
      )}
    </Stack>
  );
}
