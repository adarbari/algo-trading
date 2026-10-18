import { describe, expect, it } from 'vitest';

import { financialsTone } from './tones';

describe('financialsTone', () => {
  it.each([
    ['OK', 'positive'],
    ['PARTIAL', 'warning'],
    ['STALE', 'warning'],
    ['NO_FACTS', 'neutral'],
    ['NO_TTM', 'neutral'],
    ['NOT_COVERED', 'neutral'],
    ['FINANCIAL', 'neutral'],
    ['NOT_FETCHED', 'neutral'],
    ['BUILDING', 'neutral'],
    ['NO_PRIOR', 'neutral'],
  ] as const)('%s reads %s', (word, tone) => {
    expect(financialsTone(word)).toBe(tone);
  });

  it('ignores case and padding', () => {
    expect(financialsTone(' ok ')).toBe('positive');
  });

  it('reads an unknown word or a gap as neutral', () => {
    expect(financialsTone('SOMETHING_NEW')).toBe('neutral');
    expect(financialsTone('')).toBe('neutral');
  });
});
