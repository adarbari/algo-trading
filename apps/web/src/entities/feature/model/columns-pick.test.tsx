import { Stack } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  countsTowardColumn,
  matchedColumn,
  matchedText,
  pickEdgeWords,
  PICK_EDGE_TERM,
} from './columns-pick';
import type { ColumnInfo, PickEdge, TableRow } from './table';

const INFO = (name: string, format: string, unit: string | null, dtype = 'float64'): ColumnInfo =>
  ({
    name,
    description: '',
    format,
    unit,
    dtype,
    nullMeaning: '',
    licence: 'open',
    scope: 'site',
  }) as unknown as ColumnInfo;
const FEATURES = new Map([
  ['feature.revisions', INFO('feature.revisions', 'PERCENT', 'decimal')],
  ['feature.analysts', INFO('feature.analysts', 'NUMBER', null, 'int64')],
]);
const CRITERIA = [
  { id: 'listed', field: 'instrument.optionable', mode: 'hard' },
  { id: 'rev', field: 'feature.revisions', mode: 'hard' },
  { id: 'n', field: 'feature.analysts', mode: 'hard' },
  { id: 'miss', field: 'feature.revisions', mode: 'soft' },
];
const ROW = {
  symbol: 'AAA',
  instrumentId: 'EQ:AAA',
  name: 'A',
  cells: {},
  criteria: {
    listed: { value: 1, outcome: 'PASS' },
    rev: { value: 0.062, outcome: 'PASS' },
    n: { value: 7, outcome: 'PASS' },
    miss: { value: 0.01, outcome: 'FAIL' },
  },
} as TableRow;
const edge = (code: string, counts = false): PickEdge => ({
  edgeId: 'drift',
  edgeName: 'Drift',
  counts,
  code,
  topK: 5,
  place: null,
});

describe('matchedText', () => {
  it('lists the rules the pick passed with their values, never a gate or a miss', () => {
    expect(matchedText(ROW, CRITERIA, FEATURES)).toBe('Revisions 6.2% · Analysts 7');
  });

  it('is empty when nothing passed', () => {
    expect(matchedText({ ...ROW, criteria: {} }, CRITERIA, FEATURES)).toBe('');
  });
});

describe('matchedColumn', () => {
  it('is not sortable (the server sorts no such key) and has its Guide entry', () => {
    const column = matchedColumn(CRITERIA, FEATURES);
    expect(column.sortable).toBe(false);
    expect(column.help).toEqual({ kind: 'term', id: 'why_it_matched' });
    expect(column.value(ROW)).toBe('Revisions 6.2% · Analysts 7');
  });
});

describe('countsTowardColumn', () => {
  const cell = (row: TableRow) => {
    const column = countsTowardColumn();
    const draw = column.cell?.({
      row,
      value: column.value(row),
      formatted: { text: '', tone: 'default' },
    });
    render(<Stack>{draw}</Stack>);
  };

  it('says counted or not and why, per edge', () => {
    cell({ ...ROW, countsToward: [edge('counts', true)] });
    expect(screen.getByText('Counts')).toHaveAttribute('data-tone', 'positive');
    expect(screen.getByText('Drift')).toBeInTheDocument();
  });

  it('shows a held-back pick as not counted', () => {
    cell({ ...ROW, countsToward: [edge('paused')] });
    expect(screen.getByText('Held back by the regime gate')).toHaveAttribute(
      'data-tone',
      'neutral',
    );
  });

  it('names at most two edges and counts the rest', () => {
    const many = ['a', 'b', 'c', 'd'].map((id) => ({ ...edge('counts', true), edgeId: id }));
    cell({ ...ROW, countsToward: many });
    expect(screen.getByText('+2 more edges')).toBeInTheDocument();
  });

  it('draws nothing when no edge lists the screener', () => {
    cell({ ...ROW, countsToward: [] });
    expect(screen.queryByText('Counts')).toBeNull();
  });
});

describe('the words of each reason', () => {
  it('has a Guide term and words for every code the server sends', () => {
    for (const code of [
      'counts',
      'paused',
      'not_qualified',
      'below_top_k',
      'withheld',
      'unjudged',
    ]) {
      expect(PICK_EDGE_TERM[code]).toMatch(/^edge_pick_/);
      expect(pickEdgeWords(edge(code))).not.toBe('');
    }
  });
});
