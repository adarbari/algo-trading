import { describe, expect, it } from 'vitest';

import { reviewItems } from './items';

describe('reviewItems', () => {
  it('reads a FIGI review note and a leveraged-ETF name', () => {
    const items = reviewItems({
      session: '2026-10-02',
      source: 'universe_build',
      items: [
        { symbol: 'MMED', note: 'FIGI shared with MMEDV', vendor_figi: 'BBG01Z6N2YW2' },
        { symbol: 'CLIX', name: 'ProShares Long Online/Short Stores ETF' },
        { instrument_id: 'EQ:X' },
      ],
    });
    expect(items).toEqual([
      { symbol: 'MMED', detail: 'FIGI shared with MMEDV' },
      { symbol: 'CLIX', detail: 'ProShares Long Online/Short Stores ETF' },
      { symbol: 'EQ:X', detail: '' },
    ]);
  });
});
