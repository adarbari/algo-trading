import { describe, expect, it } from 'vitest';

import { tableVariables, toTableData } from './table';

const column = (name: string) => ({
  name,
  description: name,
  format: 'NUMBER' as const,
  unit: null,
  dtype: 'float',
  nullMeaning: '',
  licence: 'open',
  scope: 'site',
});

describe('feature table', () => {
  it('turns the columnar response into rows of cells by catalogue name', () => {
    const data = toTableData({
      session: { date: '2026-10-02', missing: ['rollups/instrument/earnings@v1'] },
      universeSnapshot: '2026-10-02',
      preSnapshot: false,
      sort: '-a.b',
      total: 11_427,
      page: 2,
      size: 100,
      missing: ['instruments/company'],
      columns: [column('rollup.a@v1.x'), column('feature.y')],
      instruments: [
        { instrumentId: 'EQ:A', symbol: 'AAPL', name: 'Apple Inc.' },
        { instrumentId: 'EQ:M', symbol: 'MRVL', name: 'Marvell' },
      ],
      rows: [
        [1.5, 'HIGH'],
        [null, null],
      ],
      unknown: [
        [null, null],
        ['NO_PARTITION', 'NULL'],
      ],
    });
    expect(data.rows.map((r) => r.symbol)).toEqual(['AAPL', 'MRVL']);
    expect(data.rows[0]?.cells).toEqual({
      'rollup.a@v1.x': { value: 1.5, unknown: null },
      'feature.y': { value: 'HIGH', unknown: null },
    });
    expect(data.rows[1]?.cells['rollup.a@v1.x']).toEqual({ value: null, unknown: 'NO_PARTITION' });
    expect([data.session, data.total, data.page, data.size]).toEqual([
      '2026-10-02',
      11_427,
      2,
      100,
    ]);
    expect(data.missing).toEqual(['rollups/instrument/earnings@v1', 'instruments/company']);
  });

  it('sends the query as the operation variables, absent parts as null', () => {
    expect(
      tableVariables({
        columns: ['feature.y'],
        filters: { securityType: 'ETF', q: 'nv' },
        sort: '-feature.y',
        page: 3,
        size: 100,
      }),
    ).toEqual({
      columns: ['feature.y'],
      keys: null,
      securityType: 'ETF',
      sector: null,
      liquidityClass: null,
      leveraged: null,
      optionable: null,
      q: 'nv',
      sort: '-feature.y',
      page: 3,
      size: 100,
    });
    const keyed = tableVariables({ columns: [], keys: ['AAPL'] });
    expect(keyed.keys).toEqual(['AAPL']);
    expect('page' in keyed || 'size' in keyed).toBe(false); // the server's defaults
  });
});
