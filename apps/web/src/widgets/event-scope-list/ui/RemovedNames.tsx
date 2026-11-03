/** The names an admin removed: who, when and why; adding one again restores it (a button here). */
import { Button, DataTable, Mono, type DataTableColumn } from '@algotrade/ui';
import { useMemo } from 'react';

import { reasonLabel, type RemovedName } from '@/entities/event-scope';
import { useAddScopeName } from '@/features/event-scope-edit';

export function RemovedNames({ removed }: { removed: readonly RemovedName[] }) {
  const add = useAddScopeName();
  const columns = useMemo<DataTableColumn<RemovedName>[]>(
    () => [
      {
        id: 'symbol',
        header: 'Ticker',
        value: (r) => r.symbol,
        mono: true,
        hideable: false,
        essential: true,
      },
      { id: 'by', header: 'Removed by', value: (r) => r.by },
      {
        id: 'at',
        header: 'On',
        value: (r) => r.at,
        cell: ({ row }) => <Mono size="sm">{row.at.slice(0, 10)}</Mono>,
      },
      {
        id: 'reasons',
        header: 'Still in scope by',
        value: (r) => r.reasons.map(reasonLabel).join(', ') || null,
        tone: 'secondary',
      },
      { id: 'note', header: 'Note', value: (r) => r.note || null, grow: true, tone: 'secondary' },
      {
        id: 'restore',
        header: 'Restore',
        value: (r) => r.symbol,
        sortable: false,
        hideable: false,
        essential: true,
        cell: ({ row }) => (
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Restore ${row.symbol}`}
            onClick={() => {
              add.mutate({ symbol: row.symbol });
            }}
          >
            Restore
          </Button>
        ),
      },
    ],
    [add],
  );
  return (
    <DataTable<RemovedName>
      label="Removed names"
      columns={columns}
      rows={[...removed]}
      getRowId={(r) => r.symbol}
      getRowLabel={(r) => r.symbol}
      sortMode="client"
      emptyMessage="No name was removed."
    />
  );
}
