import { describe, expect, it } from 'vitest';

import { toFilterInputs } from './filter';

describe('toFilterInputs', () => {
  it('sends nothing for no filters, so the read is the plain one', () => {
    expect(toFilterInputs([])).toBeNull();
  });

  it('writes each filter as the read takes it, keeping a switched-off one', () => {
    expect(
      toFilterInputs([
        { id: 'decision', values: ['QUALIFIED'], active: true },
        { id: 'dte', min: 5, active: false },
        { id: 'earn', within: { amount: 3, unit: 'days' }, active: true },
        { id: 'ex', within: { amount: 2, unit: 'sessions' }, active: true },
      ]),
    ).toEqual([
      { id: 'decision', values: ['QUALIFIED'], min: null, max: null, within: null, active: true },
      { id: 'dte', values: [], min: 5, max: null, within: null, active: false },
      {
        id: 'earn',
        values: [],
        min: null,
        max: null,
        within: { amount: 3, unit: 'DAYS' },
        active: true,
      },
      {
        id: 'ex',
        values: [],
        min: null,
        max: null,
        within: { amount: 2, unit: 'SESSIONS' },
        active: true,
      },
    ]);
  });
});
