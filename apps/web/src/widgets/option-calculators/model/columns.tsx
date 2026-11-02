/**
 * The columns of the option calculators' tables: one roll or one call per row, in the server's
 * order and figures, so these are typed structure and not instruments x catalogue features (the
 * exception list of `lint-rules/columns.js`). Each header carries its Guide help button; a chip
 * under a "watch for" heading names a thing to check before selling, never a verdict.
 */
import { Chip, Stack, Text, type DataTableCellContext, type DataTableColumn } from '@algotrade/ui';
import type { ReactNode } from 'react';

import type { CallRow, RollRow } from '@/features/option-calculators';
import { termHelp } from '@/features/guide-help';

const DATE = { kind: 'date', style: 'weekday' } as const;
const USD = { kind: 'currency' } as const;

/** The report chip of a row: it holds the company's report, or says the date is not known. */
function ReportFlag({
  inside,
  unknown,
}: {
  inside: boolean | null;
  unknown: { guide_term: string; kind_text: string } | null;
}): ReactNode {
  if (inside === true) return <Chip label="Includes report" />;
  if (unknown === null) return null;
  return (
    <Stack direction="row" gap={1} align="center">
      <Text size="sm" tone="muted">
        {unknown.kind_text}
      </Text>
      {termHelp(unknown.guide_term)}
    </Stack>
  );
}

/** The expiry with the report chip under it (the Roll table). */
function RollExpiry({ row, formatted }: DataTableCellContext<RollRow>): ReactNode {
  return (
    <Stack gap={1}>
      <Text>{formatted.text}</Text>
      <ReportFlag inside={row.report_inside} unknown={row.report_inside_unknown} />
    </Stack>
  );
}

/** The rolls: the four basic columns, then the figures that More adds. */
export function rollColumns(more: boolean): DataTableColumn<RollRow>[] {
  const basics: DataTableColumn<RollRow>[] = [
    {
      id: 'expiry',
      header: 'New expiry',
      headerAction: termHelp('roll_new_expiry'),
      value: (r) => r.expiry,
      format: DATE,
      cell: RollExpiry,
      sortable: false,
      hideable: false,
      width: 'lg',
    },
    {
      id: 'strike',
      header: 'New strike',
      headerAction: termHelp('roll_new_strike'),
      value: (r) => r.strike,
      format: USD,
      sortable: false,
      essential: true,
    },
    {
      id: 'credit',
      header: 'Extra credit',
      headerAction: termHelp('roll_extra_credit'),
      value: (r) => r.extra_credit,
      format: USD,
      sortable: false,
      essential: true,
    },
    {
      id: 'breakeven',
      header: 'New breakeven',
      headerAction: termHelp('roll_new_breakeven'),
      value: (r) => r.new_breakeven,
      format: USD,
      sortable: false,
      essential: true,
    },
  ];
  if (!more) return basics;
  return [
    ...basics,
    {
      id: 'per_day',
      header: 'Extra credit per extra day',
      headerAction: termHelp('roll_credit_per_day'),
      value: (r) => r.credit_per_extra_day,
      format: { kind: 'currency', digits: 3 },
      sortable: false,
    },
    {
      id: 'delta',
      header: 'New delta',
      headerAction: termHelp('roll_new_delta'),
      value: (r) => r.delta,
      format: { kind: 'number', digits: 2 },
      sortable: false,
    },
  ];
}

/** The chips of a call: what to check before selling it. */
function Watch({ row }: { row: CallRow }): ReactNode {
  const chips = [
    row.ex_div_before_expiry === true && 'Ex-dividend before expiry',
    row.early_exercise_risk === true && 'Early exercise risk',
  ].filter((label): label is string => label !== false);
  return (
    <Stack direction="row" gap={1} wrap align="center">
      <ReportFlag inside={row.report_inside} unknown={row.report_inside_unknown} />
      {chips.map((label) => (
        <Chip key={label} label={label} />
      ))}
    </Stack>
  );
}

/** A plain cell of a call, muted when the strike is below the trader's price. */
function Figure({ row, formatted }: DataTableCellContext<CallRow>): ReactNode {
  return <Text tone={row.below_price ? 'muted' : 'default'}>{formatted.text}</Text>;
}

/** The strike, with "below your price" under it when being called there locks in a loss. */
function Strike({ row, formatted }: DataTableCellContext<CallRow>): ReactNode {
  return (
    <Stack gap={0}>
      <Figure row={row} value={row.strike} formatted={formatted} />
      {row.below_price && (
        <Stack direction="row" gap={1} align="center">
          <Text size="sm" tone="muted">
            below your price
          </Text>
          {termHelp('calls_below_price')}
        </Stack>
      )}
    </Stack>
  );
}

/** The calls: one per strike and expiry, the server's order. */
export const callColumns: DataTableColumn<CallRow>[] = [
  {
    id: 'expiry',
    header: 'Expiry',
    headerAction: termHelp('calls_expiry'),
    value: (r) => r.expiry,
    format: DATE,
    cell: Figure,
    sortable: false,
    hideable: false,
  },
  {
    id: 'strike',
    header: 'Strike',
    headerAction: termHelp('grid_strike'),
    value: (r) => r.strike,
    format: USD,
    cell: Strike,
    sortable: false,
    essential: true,
    width: 'lg',
  },
  {
    id: 'premium',
    header: 'Premium',
    headerAction: termHelp('calls_premium'),
    value: (r) => r.premium,
    format: USD,
    cell: Figure,
    sortable: false,
    essential: true,
  },
  {
    id: 'over_price',
    header: 'Premium ÷ your price',
    headerAction: termHelp('calls_premium_over_price'),
    value: (r) => r.premium_over_price,
    format: { kind: 'percent', digits: 2 },
    cell: Figure,
    sortable: false,
    essential: true,
  },
  {
    id: 'called',
    header: 'If called away',
    headerAction: termHelp('calls_if_called'),
    value: (r) => r.if_called,
    format: { kind: 'percent', digits: 1 },
    cell: Figure,
    sortable: false,
  },
  {
    id: 'total',
    header: 'Total premium',
    headerAction: termHelp('calls_premium_total'),
    value: (r) => r.premium_total,
    format: USD,
    cell: Figure,
    sortable: false,
  },
  {
    id: 'watch',
    header: 'Watch for',
    headerAction: termHelp('calls_watch_for'),
    value: (r) => r.early_exercise_risk,
    cell: ({ row }) => <Watch row={row} />,
    sortable: false,
    grow: true,
    width: 'xl',
  },
];
