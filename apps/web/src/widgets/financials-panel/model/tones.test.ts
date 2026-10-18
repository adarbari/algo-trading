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

  it('reads the rating and revision statuses: OK positive, STALE warning, the rest neutral', () => {
    // ratings_status: OK / STALE / NOT_COVERED / NOT_FETCHED; revisions_status adds BUILDING / NO_PRIOR
    const words = ['OK', 'STALE', 'NOT_COVERED', 'NOT_FETCHED', 'BUILDING', 'NO_PRIOR'];
    expect(words.map(financialsTone)).toEqual([
      'positive',
      'warning',
      'neutral',
      'neutral',
      'neutral',
      'neutral',
    ]);
  });

  it('ignores case and padding', () => {
    expect(financialsTone(' ok ')).toBe('positive');
  });

  it('reads an unknown word or a gap as neutral', () => {
    expect(financialsTone('SOMETHING_NEW')).toBe('neutral');
    expect(financialsTone('')).toBe('neutral');
  });
});
