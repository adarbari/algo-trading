/**
 * FormulaPreview: the dry run of a draft formula, for the trader to review before it is added: the
 * formula in monospace, a line for its inputs and unit, a StatStrip of how it behaved (rows
 * checked, share with no value, range, how many pass) and a small sample table of real rows.
 * `actions` holds the decision (Review and add / Skip). It shows numbers and names it is given;
 * every label and sentence arrives as a prop.
 */
import type { ReactNode } from 'react';

import type { ValueFormat } from '../../format';
import { Mono } from '../../primitives/Mono';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { DataTable, type DataTableColumn } from '../DataTable';
import { StatStrip, type StatItem } from '../StatStrip';
import styles from './FormulaPreview.module.css';

export interface FormulaSampleRow {
  /** Stable row id. */
  id: string;
  /** The row's name (a ticker). */
  label: string;
  /** The value of each sample column, by column id; `null` is a missing value. */
  values: Readonly<Record<string, number | null>>;
}

export interface FormulaSample {
  /** Accessible name of the sample table. */
  label: string;
  /** Header of the name column ("Symbol"). */
  labelHeader: string;
  /** The value columns, in order (the inputs, then the formula's result). */
  columns: readonly { id: string; header: string; format?: ValueFormat }[];
  rows: readonly FormulaSampleRow[];
}

export interface FormulaPreviewProps {
  /** The draft feature's name, set in mono above the formula. */
  name?: string;
  /** The formula, e.g. `close / price_stats.high_52w - 1`. */
  formula: string;
  /** The inputs and the unit, one muted line ("Inputs: close, price_stats.high_52w · ratio"). */
  inputs?: ReactNode;
  /** The dry-run figures (rows checked, no-value rate, range, passing). */
  stats: readonly StatItem[];
  /** Accessible name of the stat strip. */
  statsLabel: string;
  /** A few real rows run through the formula. */
  sample?: FormulaSample | undefined;
  /** The decision: Review and add / Skip buttons. */
  actions?: ReactNode | undefined;
}

type Row = FormulaSampleRow;

export function FormulaPreview({
  name,
  formula,
  inputs,
  stats,
  statsLabel,
  sample,
  actions,
}: FormulaPreviewProps) {
  const columns: DataTableColumn<Row>[] = sample
    ? [
        {
          id: 'label',
          header: sample.labelHeader,
          value: (row) => row.label,
          cell: ({ row }) => <Mono>{row.label}</Mono>,
          sortable: false,
          hideable: false,
          essential: true,
        },
        ...sample.columns.map((column): DataTableColumn<Row> => ({
          id: column.id,
          header: column.header,
          value: (row) => row.values[column.id] ?? null,
          format: column.format ?? { kind: 'number', digits: 2 },
          sortable: false,
          essential: true,
        })),
      ]
    : [];
  return (
    <Stack gap={3}>
      <div className={styles.formula}>
        {name && <Mono>{name}</Mono>}
        <code className={styles.code}>{formula}</code>
        {inputs && (
          <Text size="sm" tone="muted">
            {inputs}
          </Text>
        )}
      </div>
      <StatStrip items={stats} label={statsLabel} />
      {sample && sample.rows.length > 0 && (
        <DataTable
          label={sample.label}
          columns={columns}
          rows={sample.rows}
          getRowId={(row) => row.id}
          columnPicker={false}
          visibleRows={sample.rows.length}
        />
      )}
      {actions && (
        <Stack direction="row" gap={2} wrap>
          {actions}
        </Stack>
      )}
    </Stack>
  );
}
