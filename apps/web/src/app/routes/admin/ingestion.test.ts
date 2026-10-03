import { describe, expect, it } from 'vitest';

import { validateIngestionSearch } from './ingestion';

describe('validateIngestionSearch', () => {
  it('keeps a dataset with an ISO session, else nothing', () => {
    const cell = { dataset: 'chains/option_quotes', session: '2026-10-02' };
    expect(validateIngestionSearch(cell)).toEqual(cell);
    expect(validateIngestionSearch({ dataset: 'bars/1d', session: 'friday' })).toEqual({});
    expect(validateIngestionSearch({ dataset: 'bars/1d' })).toEqual({});
    expect(validateIngestionSearch({})).toEqual({});
  });
});
