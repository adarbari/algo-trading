import { DataTable } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import {
  changeColumn,
  criterionColumn,
  decisionColumn,
  featureColumn,
  flagsColumn,
  rankColumn,
  reasonsColumn,
  scoreColumn,
  screenColumn,
  tickerColumn,
  type ColumnPlan,
} from './columns';
import type { ColumnInfo, TableRow } from './table';

stubElementSize();

const info = (name: string, patch: Partial<ColumnInfo> = {}): ColumnInfo => ({
  name,
  description: `About ${name}`,
  format: 'NUMBER',
  unit: null,
  dtype: 'float',
  nullMeaning: '',
  licence: 'open',
  scope: 'site',
  ...patch,
});

const CLOSE = info('rollup.price_stats@v2.close', { format: 'CURRENCY', unit: 'usd_per_share' });
const EARN = info('rollup.earnings@v1.days_to_earnings', {
  format: 'NUMBER',
  unit: 'days',
  dtype: 'int',
  nullMeaning: 'no upcoming report known',
});
const IV = info('rollup.ibkr_iv@v1.iv30', { format: 'PERCENT', licence: 'personal' });

const rows: TableRow[] = [
  {
    symbol: 'MRVL',
    instrumentId: 'EQ:M',
    name: 'Marvell Technology',
    cells: {
      [CLOSE.name]: { value: 71.5, unknown: null },
      [EARN.name]: { value: null, unknown: 'NO_PARTITION' },
      [IV.name]: { value: 0.42, unknown: null },
    },
    rank: 1,
    decision: 'EVENT_RISK',
    score: 87.4,
    flags: ['large_move'],
    criteria: { iv: { value: 0.42, outcome: 'NEAR' } },
    change: 'new',
  },
  {
    symbol: 'AAPL',
    instrumentId: 'EQ:A',
    name: 'Apple Inc.',
    cells: {
      [CLOSE.name]: { value: 255.1, unknown: null },
      [EARN.name]: { value: 23, unknown: null },
    },
  },
];

function table(plan: ColumnPlan) {
  return render(
    <DataTable columns={plan} rows={rows} getRowId={(r) => r.symbol} label="Plan" rowLines={2} />,
  );
}

describe('column factories', () => {
  it('give each column a stable id that is its server sort key', () => {
    const plan = [
      rankColumn(),
      tickerColumn(),
      decisionColumn(),
      scoreColumn(),
      criterionColumn({ id: 'iv', field: IV.name, mode: 'soft' }, IV),
      featureColumn(CLOSE),
      flagsColumn(),
      changeColumn(),
      screenColumn({ name: 'close', field: CLOSE.name }, CLOSE),
      reasonsColumn(),
    ];
    expect(plan.map((c) => c.id)).toEqual([
      'rank',
      'symbol',
      'decision',
      'score',
      'criterion:iv',
      CLOSE.name,
      'flags',
      'change',
      'column:close',
      'reasons',
    ]);
  });

  it('format a feature from the server format and say UNKNOWN with the reason', async () => {
    const { container } = table([tickerColumn(), featureColumn(CLOSE), featureColumn(EARN)]);
    const grid = screen.getByRole('grid', { name: 'Plan' });
    expect(within(grid).getByText('$71.50')).toBeInTheDocument();
    expect(within(grid).getByText('23')).toBeInTheDocument();
    const unknown = within(grid).getByText('Unknown');
    expect(unknown).toHaveAttribute('title', 'not stored for this session');
    expect(within(grid).getByText('Marvell Technology')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Earn\./ })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('mark personal-licence features and describe a column from its catalogue entry', () => {
    const column = featureColumn(IV);
    expect(column.header).toBe('Iv30 (P)');
    expect(column.description).toBe(`About ${IV.name} (personal licence) [${IV.name}]`);
    expect(column.format).toEqual({ kind: 'percent' });
    expect(featureColumn(EARN).description).toContain('Unit: days.');
    const nul = featureColumn(EARN);
    const row = rows[0] as TableRow;
    expect(nul.value(row)).toBeNull(); // sorts last
  });

  it('render screen results: decision badge, tinted criterion, flags and change', () => {
    table([
      rankColumn(),
      tickerColumn(),
      decisionColumn(),
      scoreColumn(),
      criterionColumn({ id: 'iv', field: IV.name, mode: 'soft' }, IV),
      flagsColumn(),
      changeColumn(),
    ]);
    const grid = screen.getByRole('grid', { name: 'Plan' });
    expect(within(grid).getByText('Event risk')).toBeInTheDocument();
    expect(within(grid).getByText('87')).toBeInTheDocument();
    expect(within(grid).getByText(/^42(\.0)?%$/)).toBeInTheDocument();
    expect(within(grid).getByText('Large move')).toBeInTheDocument();
    expect(within(grid).getByText('New')).toBeInTheDocument();
    const criterion = criterionColumn({ id: 'iv', field: IV.name, mode: 'soft' });
    expect(criterion.fill?.(rows[0] as TableRow)).toBe('warning');
    expect(criterion.fill?.(rows[1] as TableRow)).toBeUndefined();
    expect(criterion.header).toBe('Iv');
  });

  it('render what a run stored: display columns, why, what it was, who would leave', () => {
    const stored: TableRow = {
      ...(rows[0] as TableRow),
      decision: 'REJECT',
      change: 'dropped',
      previousDecision: 'EVENT_RISK',
      columns: { close: 70.25, ratio: 1.234 },
      reasons: 'iv30 below 50%',
    };
    render(
      <DataTable
        columns={[
          tickerColumn(),
          decisionColumn(new Set(['MRVL'])),
          screenColumn({ name: 'close', field: CLOSE.name }, CLOSE),
          screenColumn({ name: 'iv_hv_ratio', field: 'feature.iv_hv_ratio' }),
          changeColumn(),
          reasonsColumn(),
        ]}
        rows={[{ ...stored, columns: { close: 70.25, iv_hv_ratio: 1.234 } }]}
        getRowId={(r) => r.symbol}
        label="Stored"
        rowLines={2}
      />,
    );
    const grid = screen.getByRole('grid', { name: 'Stored' });
    expect(within(grid).getByText('Would leave')).toBeInTheDocument();
    expect(within(grid).getByText('$70.25')).toBeInTheDocument();
    expect(within(grid).getByText('1.23')).toBeInTheDocument();
    expect(within(grid).getByText('Dropped (was event risk)')).toBeInTheDocument();
    expect(within(grid).getByText('iv30 below 50%')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Iv hv ratio/ })).toBeInTheDocument();
  });
});
