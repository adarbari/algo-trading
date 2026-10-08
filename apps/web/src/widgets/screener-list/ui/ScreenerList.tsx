/**
 * The screeners: the user's own (finalized and draft-only: open to edit) and the site presets
 * (open to see the live preview, or "Copy to my screeners", which pins the preset's version).
 * Your own can be deleted (after a confirmation).
 * Python screeners are listed but built in code.
 */
import { DataTable, Panel, Stack } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { useMyScreeners, useScreeners, type ScreenerSummary } from '@/entities/screen';
import { CopyPresetDialog } from '@/features/screener-copy';
import { DeleteScreenerDialog } from '@/features/screener-delete';

import { myColumns, presetColumns, type MyScreener } from '../model/columns';

export interface ScreenerListProps {
  /** Open a screener's results. */
  onOpen: (id: string) => void;
  /** Open a screener in the Builder (a new copy opens there: it has no run yet). */
  onEdit: (id: string) => void;
}

export function ScreenerList({ onOpen, onEdit }: ScreenerListProps) {
  const configs = useScreeners();
  const mine = useMyScreeners();
  const [copying, setCopying] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const actions = useMemo(
    () => ({ onOpen, onEdit, onCopy: setCopying, onDelete: setDeleting }),
    [onOpen, onEdit],
  );
  const presetCols = useMemo(() => presetColumns(actions), [actions]);
  const myCols = useMemo(() => myColumns(actions), [actions]);
  const all = configs.data ?? [];
  const presets = all.filter((s) => s.scope === 'site');
  const resolved = new Map(all.filter((s) => s.scope !== 'site').map((s) => [s.configId, s]));
  const own: MyScreener[] = (mine.data ?? []).map((s) => ({
    ...s,
    selection: resolved.get(s.screenerId)?.selection ?? null,
    error: resolved.get(s.screenerId)?.error ?? null,
  }));
  const stateOf = (query: { isError: boolean; isPending: boolean; data: unknown }) =>
    query.isError && !query.data ? 'error' : query.isPending ? 'loading' : 'ready';
  return (
    <Stack gap={4}>
      <Panel
        title="Your screeners"
        description="Finalized screeners and drafts; a copy of a preset appears here once you edit it"
        flush
        state={stateOf(mine)}
        loadingLabel="Loading screeners…"
        errorMessage="The screeners failed to load."
        onRetry={() => void mine.refetch()}
      >
        <DataTable<MyScreener>
          label="Your screeners"
          columns={myCols}
          rows={own}
          getRowId={(s) => s.screenerId}
          getRowLabel={(s) => s.screenerId}
          onRowActivate={(s) => {
            onOpen(s.screenerId);
          }}
          defaultSort={{ columnId: 'name', direction: 'asc' }}
          emptyMessage="You have no screener yet. Create one, or open a preset and change it."
        />
      </Panel>
      <Panel
        title="Site presets"
        description="Open one to see its live preview; change anything and a copy becomes yours"
        flush
        state={stateOf(configs)}
        loadingLabel="Loading presets…"
        errorMessage="The presets failed to load."
        onRetry={() => void configs.refetch()}
      >
        <DataTable<ScreenerSummary>
          label="Site presets"
          columns={presetCols}
          rows={presets}
          getRowId={(s) => s.configId}
          getRowLabel={(s) => s.configId}
          onRowActivate={(s) => {
            if (s.impl === 'rules') onOpen(s.configId);
          }}
          defaultSort={{ columnId: 'name', direction: 'asc' }}
          emptyMessage="No site screener presets."
        />
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
            onEdit(id);
          }}
        />
      )}
      {deleting && (
        <DeleteScreenerDialog
          screenerId={deleting}
          open
          onOpenChange={(open) => {
            if (!open) setDeleting(null);
          }}
          onDeleted={() => {
            setDeleting(null);
          }}
        />
      )}
    </Stack>
  );
}
