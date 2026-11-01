import { describe, expect, it } from 'vitest';

import { verdictTone } from './verdict';

describe('verdictTone', () => {
  it('tints each verdict', () => {
    expect(verdictTone('works')).toBe('positive');
    expect(verdictTone('promising')).toBe('accent');
    expect(verdictTone('too_few_cases')).toBe('warning');
    expect(verdictTone('baseline')).toBe('neutral');
  });

  it('reads an unknown verdict as neutral', () => {
    expect(verdictTone('something_new')).toBe('neutral');
  });
});
