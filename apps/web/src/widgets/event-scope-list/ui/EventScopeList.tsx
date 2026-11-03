/**
 * The event-study scope list for the session: a headline strip (names, stale reviews, the other
 * names in scope, the macro calendar's reach) over the table of listed names, the add form, the
 * symbols the session cannot resolve and the names an admin removed (adding one restores it).
 * Every figure is the server's; the strip only counts the rows it was sent.
 */
import { Banner, DataTable, Mono, Panel, Stack, StatStrip, formatValue } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { UnknownNote } from '@/entities/availability';
import {
  START_PAGE,
  TERM_OF_ADD,
  TERM_OF_MACRO,
  TERM_OF_REMOVED,
  TERM_OF_UNRESOLVED,
  useEventScope,
  type ScopeName,
} from '@/entities/event-scope';
import { AddScopeNameForm, RemoveScopeNameDialog } from '@/features/event-scope-edit';
import { GuideHelp, termHelp } from '@/features/guide-help';

import { scopeColumns } from '../model/columns';
import { RemovedNames } from './RemovedNames';

const count = (n: number) => formatValue(n, { kind: 'number' }).text;

export function EventScopeList() {
  const scope = useEventScope();
  const [removing, setRemoving] = useState<string | null>(null);
  const columns = useMemo(() => scopeColumns(setRemoving), []);
  const data = scope.data;
  const names = data?.names ?? [];
  const state =
    scope.isError && !data
      ? 'error'
      : scope.isPending
        ? 'loading'
        : data == null || names.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Stack gap={4}>
      <StatStrip
        label="Scope summary"
        loading={scope.isPending}
        items={[
          { id: 'names', label: 'Listed names', value: data ? count(names.length) : '—' },
          {
            id: 'stale',
            label: 'Stale reviews',
            value: data ? count(data.staleCount) : '—',
            tone: data && data.staleCount > 0 ? 'warning' : 'default',
          },
          {
            id: 'other',
            label: 'Other names in scope',
            value: data ? count(data.otherNames) : '—',
          },
          {
            id: 'macro',
            label: data
              ? `Macro releases, next ${String(data.macroDays)} days`
              : 'Macro releases ahead',
            value:
              data?.macroReleases == null ? (
                data?.macroUnknown ? (
                  <UnknownNote unknown={data.macroUnknown} />
                ) : (
                  '—'
                )
              ) : (
                count(data.macroReleases)
              ),
            sub: termHelp(TERM_OF_MACRO),
          },
        ]}
      />
      {data && data.unresolved.length > 0 && (
        <Banner tone="warning" actions={termHelp(TERM_OF_UNRESOLVED)}>
          {data.unresolved.map((s) => (
            <Mono key={s}>{s} </Mono>
          ))}
        </Banner>
      )}
      <Panel title="Add a ticker" actions={termHelp(TERM_OF_ADD)}>
        <AddScopeNameForm />
      </Panel>
      <Panel
        title="Scope list"
        flush
        state={state}
        loadingLabel="Loading the scope list…"
        emptyMessage="No name is listed."
        errorMessage="The scope list failed to load."
        onRetry={() => void scope.refetch()}
        actions={<GuideHelp entry={{ kind: 'start', id: START_PAGE }} />}
      >
        <DataTable<ScopeName>
          label="Scope list"
          columns={columns}
          rows={names}
          getRowId={(n) => n.instrumentId}
          getRowLabel={(n) => n.symbol}
          sortMode="client"
          emptyMessage="No name is listed."
        />
      </Panel>
      {data && data.removed.length > 0 && (
        <Panel title="Removed by an admin" actions={termHelp(TERM_OF_REMOVED)} flush>
          <RemovedNames removed={data.removed} />
        </Panel>
      )}
      {removing && (
        <RemoveScopeNameDialog
          symbol={removing}
          open
          onOpenChange={(open) => {
            if (!open) setRemoving(null);
          }}
        />
      )}
    </Stack>
  );
}
