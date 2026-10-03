import { describe, expect, it } from 'vitest';

import { datasetLabel, isChains } from './dataset';

describe('datasetLabel', () => {
  it('names the known tables and derives the rest', () => {
    expect(datasetLabel('bars/1d')).toBe('Daily bars');
    expect(datasetLabel('chains/option_quotes')).toBe('Option chains');
    expect(datasetLabel('rollups/instrument/price_stats@v2')).toBe('Price stats (v2)');
    expect(datasetLabel('rollups/instrument/iv30@v1')).toBe('IV30 (v1)');
    expect(datasetLabel('rollups/instrument/iv_history@v2')).toBe('IV history (v2)');
    expect(datasetLabel('events/earnings')).toBe('Earnings');
  });

  it('knows the chains', () => {
    expect(isChains('chains/option_quotes')).toBe(true);
    expect(isChains('bars/1d')).toBe(false);
  });
});
