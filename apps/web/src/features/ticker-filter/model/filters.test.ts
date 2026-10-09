import { describe, expect, it } from 'vitest';

import { typeLabel } from './filters';

describe('typeLabel', () => {
  it('names the common types and spells out the rest', () => {
    expect(typeLabel('COMMON_STOCK')).toBe('Stock');
    expect(typeLabel('ETF')).toBe('ETF');
    expect(typeLabel('PREFERRED_STOCK')).toBe('Preferred stock');
  });
});
