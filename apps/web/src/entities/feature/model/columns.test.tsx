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
  fromHighColumn,
  rankColumn,
  reasonsColumn,
  scoreColumn,
  screenColumn,
  tickerColumn,
  withCompanions,
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
      [EARN.name]: {
        value: null,
        unknown: 'NO_PARTITION',
        kind: 'SYSTEM',
        kindText: 'not available because of a system error',
      },
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
    expect(unknown).toHaveAttribute('title', 'not available because of a system error');
    expect(within(grid).getByText('Marvell Technology')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Earn\./ })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('say n/a and Illiquid, not Unknown, where the server says the value cannot exist', () => {
    const etf: TableRow = {
      symbol: 'SPY',
      instrumentId: 'EQ:S',
      name: 'SPDR S&P 500',
      cells: {
        [EARN.name]: {
          value: null,
          unknown: 'NOT_APPLICABLE',
          kind: 'NOT_APPLICABLE',
          kindText: 'does not apply to this instrument',
        },
        [IV.name]: {
          value: null,
          unknown: 'ILLIQUID',
          kind: 'ILLIQUID',
          kindText: 'not available: too thinly traded today',
        },
      },
    };
    render(
      <DataTable
        columns={[tickerColumn(), featureColumn(EARN), featureColumn(IV)]}
        rows={[etf]}
        getRowId={(r) => r.symbol}
        label="Thin"
        rowLines={2}
      />,
    );
    const grid = screen.getByRole('grid', { name: 'Thin' });
    expect(within(grid).getByText('n/a')).toHaveAttribute(
      'title',
      expect.stringMatching(/does not apply/),
    );
    expect(within(grid).getByText('Illiquid')).toHaveAttribute(
      'title',
      expect.stringMatching(/thinly traded/),
    );
    expect(within(grid).queryByText('Unknown')).not.toBeInTheDocument();
  });

  it('say what an explained absence is, not Unknown (ADR 0046)', () => {
    const quiet: TableRow = {
      symbol: 'THIN',
      instrumentId: 'EQ:T',
      name: 'Thin Co',
      cells: { [EARN.name]: { value: null, unknown: 'EXPLAINED', reason: 'NO_TRADE' } },
    };
    render(
      <DataTable
        columns={[tickerColumn(), featureColumn(EARN)]}
        rows={[quiet]}
        getRowId={(r) => r.symbol}
        label="Explained"
        rowLines={2}
      />,
    );
    const grid = screen.getByRole('grid', { name: 'Explained' });
    expect(within(grid).getByText('No trade')).toHaveAttribute(
      'title',
      'no trade on this session: no bar',
    );
    expect(within(grid).queryByText('Unknown')).not.toBeInTheDocument();
  });

  it('title the from-high column with its window, and ask for the window beside it', () => {
    const high = info('feature.pct_from_high_avail', { format: 'PERCENT' });
    const sessions = 'rollup.price_history@v1.range_sessions';
    const row: TableRow = {
      symbol: 'NEW',
      instrumentId: 'EQ:N',
      name: 'New Co',
      cells: {
        [high.name]: { value: -0.12, unknown: null },
        [sessions]: { value: 131, unknown: null },
      },
    };
    render(
      <DataTable
        columns={[tickerColumn(), fromHighColumn(high)]}
        rows={[row]}
        getRowId={(r) => r.symbol}
        label="High"
        rowLines={2}
      />,
    );
    const grid = screen.getByRole('grid', { name: 'High' });
    expect(within(grid).getByText(/12/)).toHaveAttribute('title', 'High over 131 sessions');
    expect(withCompanions([high.name, 'feature.x'])).toEqual([high.name, 'feature.x', sessions]);
    expect(withCompanions([high.name, sessions])).toEqual([high.name, sessions]);
  });

  it('name the Guide entry of every field column, and of no other', () => {
    const entry = { kind: 'field', id: CLOSE.name };
    expect(featureColumn(CLOSE).help).toEqual(entry);
    expect(fromHighColumn(CLOSE).help).toEqual(entry);
    expect(screenColumn({ name: 'close', field: CLOSE.name }, CLOSE).help).toEqual(entry);
    expect(criterionColumn({ id: 'c1', field: CLOSE.name, mode: 'hard' }, CLOSE).help).toEqual(
      entry,
    );
    // No catalogue entry (a screen's own column), or not a field at all: nothing to explain.
    expect(screenColumn({ name: 'close', field: CLOSE.name }).help).toBeUndefined();
    expect(criterionColumn({ id: 'c1', field: CLOSE.name, mode: 'hard' }).help).toBeUndefined();
    const others: ColumnPlan = [tickerColumn(), rankColumn(), decisionColumn(), scoreColumn()];
    for (const column of others) expect(column.help).toBeUndefined();
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
