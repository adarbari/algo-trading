/**
 * The columns of one setup's picks (rank, ticker, its place in the setup, the other setups that
 * picked it): one pick per row, the server's order and figures, so these are typed structure and
 * not instruments x catalogue features (the exception list of `lint-rules/columns.js`). On the
 * Premium tab the example position's columns follow, each header with its Guide help button.
 */
import { Mono, Stack, Text, type DataTableCellContext, type DataTableColumn } from '@algotrade/ui';
import type { ReactNode } from 'react';

import type { SetupIdea } from '@/entities/idea';
import { termHelp } from '@/features/guide-help';

export const pickColumns = (names: ReadonlyMap<string, string>): DataTableColumn<SetupIdea>[] => [
  { id: 'rank', header: 'Rank', value: (i) => i.rank, format: { kind: 'number', digits: 0 } },
  {
    id: 'ticker',
    header: 'Ticker',
    value: (i) => i.symbol ?? i.instrumentId,
    cell: ({ row }) => (
      <Stack gap={0}>
        <Mono>{row.symbol ?? row.instrumentId}</Mono>
        {row.name && (
          <Text size="sm" tone="muted">
            {row.name}
          </Text>
        )}
      </Stack>
    ),
  },
  { id: 'place', header: 'Place', value: (i) => i.place, format: { kind: 'number', digits: 0 } },
  {
    id: 'also',
    header: 'Also in',
    value: (i) => i.alsoIn.map((a) => names.get(a.edgeId) ?? a.edgeName).join(', ') || null,
  },
];

const USD = { kind: 'currency', digits: 0 } as const;
const SHARE = { kind: 'percent', digits: 1 } as const;

/** The example position's legs, signed (negative: sold), with the nearest expiry; or why none. */
function ExampleCell({ row }: DataTableCellContext<SetupIdea>): ReactNode {
  const option = row.option;
  if (!option) return null;
  if (option.unknown) {
    return (
      <Stack direction="row" gap={1} align="center">
        <Text size="sm" tone="muted">
          {option.unknown.kindText}
        </Text>
        {termHelp(option.unknown.guideTerm)}
      </Stack>
    );
  }
  return (
    <Stack gap={0}>
      {option.legs.map((leg) => (
        <Mono key={`${leg.right}${String(leg.strike)}${leg.expiry}`}>
          {`${leg.qty > 0 ? '+' : ''}${String(leg.qty)} ${leg.right} ${String(leg.strike)}`}
        </Mono>
      ))}
      {option.expiry && (
        <Text size="sm" tone="muted">
          {option.expiry}
        </Text>
      )}
    </Stack>
  );
}

/** The Premium tab's option columns (O3): the example position and its derived figures. */
export const premiumColumns = (): DataTableColumn<SetupIdea>[] => [
  {
    id: 'example',
    header: 'Example option',
    headerAction: termHelp('premium_example_option'),
    value: (i) => i.option?.expiry ?? null,
    cell: ExampleCell,
    sortable: false,
  },
  {
    id: 'credit',
    header: 'Credit',
    headerAction: termHelp('premium_credit'),
    value: (i) => i.option?.credit ?? null,
    format: USD,
  },
  {
    id: 'collateral',
    header: 'Collateral',
    headerAction: termHelp('setup_collateral'),
    value: (i) => i.option?.collateral ?? null,
    format: USD,
  },
  {
    id: 'roc',
    header: 'Return on collateral',
    headerAction: termHelp('return_on_collateral'),
    value: (i) => i.option?.returnOnCollateral ?? null,
    format: SHARE,
  },
  {
    id: 'assignment',
    header: 'Chance of assignment',
    headerAction: termHelp('premium_assignment_chance'),
    value: (i) => i.option?.assignmentChance ?? null,
    format: { kind: 'percent', digits: 0 },
  },
];
