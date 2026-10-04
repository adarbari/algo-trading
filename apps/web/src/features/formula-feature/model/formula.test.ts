import { describe, expect, it } from 'vitest';

import { guessUnit, isFeatureName, UNITS } from './formula';

describe('formula naming', () => {
  it('accepts lowercase names the API accepts', () => {
    expect(isFeatureName('vol_gap2')).toBe(true);
    expect(isFeatureName('Vol')).toBe(false);
    expect(isFeatureName('2vol')).toBe(false);
    expect(isFeatureName('')).toBe(false);
  });

  it('guesses a unit from the type, always one the feature framework knows', () => {
    expect(guessUnit('bool')).toBe('flag');
    expect(guessUnit('date')).toBe('date');
    expect(guessUnit('str')).toBe('category');
    expect(guessUnit('float32')).toBe('ratio');
    for (const dtype of ['bool', 'date', 'str', 'float']) expect(UNITS).toContain(guessUnit(dtype));
  });
});
