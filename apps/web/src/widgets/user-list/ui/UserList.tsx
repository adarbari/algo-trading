/**
 * The declared people: a headline strip (people, admins, traders) over the table, in the order
 * the site config declares them. The scheduled-screens user is not a person and is left out of
 * the counts. Nothing is derived beyond counting the rows the server sent.
 */
import { DataTable, formatValue, Panel, Stack, StatStrip } from '@algotrade/ui';
import { useMemo } from 'react';

import { TERM_OF_PERSON, useUserRegistry, type Person } from '@/entities/user-registry';
import { termHelp } from '@/features/guide-help';

import { personColumns } from '../model/columns';

const count = (n: number) => formatValue(n, { kind: 'number' }).text;

export function UserList() {
  const registry = useUserRegistry();
  const columns = useMemo(() => personColumns(), []);
  const rows = registry.data?.people ?? [];
  const people = rows.filter((p) => !p.scheduled);
  const admins = people.filter((p) => p.role === 'admin').length;
  const state =
    registry.isError && !registry.data
      ? 'error'
      : registry.isPending
        ? 'loading'
        : rows.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Stack gap={4}>
      <StatStrip
        label="People summary"
        loading={registry.isPending}
        items={[
          { id: 'people', label: 'People', value: count(people.length) },
          { id: 'admins', label: 'Admins', value: count(admins) },
          { id: 'traders', label: 'Traders', value: count(people.length - admins) },
        ]}
      />
      <Panel
        title="People"
        actions={termHelp(TERM_OF_PERSON)}
        flush
        state={state}
        loadingLabel="Loading people…"
        emptyMessage="No user is declared."
        errorMessage="The people failed to load."
        onRetry={() => void registry.refetch()}
      >
        <DataTable<Person>
          label="People"
          columns={columns}
          rows={rows}
          getRowId={(p) => p.id}
          getRowLabel={(p) => p.id}
          sortMode="client"
          emptyMessage="No user is declared."
        />
      </Panel>
    </Stack>
  );
}
