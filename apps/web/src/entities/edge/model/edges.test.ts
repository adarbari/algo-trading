import { describe, expect, it } from 'vitest';

import { statusLabel, statusTone, verdictLabel, verdictTone, VERDICT_ORDER } from './edges';

describe('status words', () => {
  it('capitalises the status and gives each a tone', () => {
    expect(statusLabel('candidate')).toBe('Candidate');
    expect(statusTone('evidenced')).toBe('positive');
    expect(statusTone('rejected')).toBe('negative');
    expect(statusTone('anything else')).toBe('neutral');
  });
});

describe('verdict words', () => {
  it('words and tones every served verdict, best first', () => {
    expect(VERDICT_ORDER.map(verdictLabel)).toEqual([
      'Works',
      'Promising',
      'Not working',
      'Not enough data',
      'Waiting on data',
    ]);
    expect(verdictTone('works')).toBe('positive');
    expect(verdictTone('not_working')).toBe('negative');
    expect(verdictTone('something else')).toBe('neutral');
    expect(verdictLabel('something else')).toBe('something else');
  });
});
