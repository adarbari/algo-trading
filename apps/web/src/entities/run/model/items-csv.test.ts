import { describe, expect, it } from 'vitest';

import { itemsCsv, itemsFileName } from './items-csv';

describe('itemsCsv', () => {
  it('writes a header and quotes fields that need it', () => {
    const csv = itemsCsv([
      { key: 'AAPL', code: 'OK', status: 'OK' },
      { key: 'E', code: 'FETCH_ERROR', status: 'FETCH_ERROR: "bad", retry' },
    ]);
    expect(csv).toBe('key,code,status\nAAPL,OK,OK\nE,FETCH_ERROR,"FETCH_ERROR: ""bad"", retry"\n');
  });

  it('names the file after the run', () => {
    expect(itemsFileName('option_chains-2026-10-02-20261003T093502Z')).toBe(
      'option_chains-2026-10-02-20261003T093502Z-items.csv',
    );
    expect(itemsFileName('a/b c')).toBe('a_b_c-items.csv');
  });
});
