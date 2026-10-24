import { describe, expect, it } from 'vitest';

import type { FilterDefinition, FilterFacets } from '@/entities/filter';

import { chipItems, countLine, groupCounts, recoveryItems, valueText } from './surface';
import type { FilterState } from './state';

const def = (id: string, label: string, group: FilterDefinition['group']): FilterDefinition => ({
  id,
  label,
  group,
  kind: 'PICK',
  guide: `term:filter_${id}`,
  options: id === 'decision' ? [{ value: 'QUALIFIED', label: 'Qualified' }] : [],
  bins: [],
  windowUnit: null,
  unit: null,
});
const DEFS = [def('decision', 'Decision', 'SETUP'), def('earnings', 'Earnings', 'COMING_UP')];
const facet = (id: string, removes: number | null, unknown = 0) => ({
  id,
  active: true,
  removes,
  unknown,
  options: [],
  bins: [],
});
const FACETS: FilterFacets = {
  total: 340,
  matched: 12,
  items: [facet('decision', 5, 3), facet('earnings', 20)],
};

describe('valueText', () => {
  it('names pick values by their option label, and keeps an unlabelled value', () => {
    expect(valueText({ id: 'decision', values: ['QUALIFIED', 'X'], active: true }, DEFS[0])).toBe(
      'Qualified, X',
    );
  });

  it('names a stored value through the caller when the definition does not label it', () => {
    const filter: FilterState = { id: 'screener', values: ['vrp', 'zz'], active: true };
    const labelOf = (_id: string, value: string) => (value === 'vrp' ? 'VRP scanner' : undefined);
    expect(valueText(filter, undefined, labelOf)).toBe('VRP scanner, zz');
    expect(
      valueText({ ...filter, id: 'decision', values: ['QUALIFIED'] }, DEFS[0], () => 'Q'),
    ).toBe('Q');
  });

  it('writes a range by its ends and a window by its size and unit', () => {
    const f = (patch: Partial<FilterState>): FilterState => ({ id: 'r', active: true, ...patch });
    expect(valueText(f({ min: 30, max: 70 }), undefined)).toBe('30–70');
    expect(valueText(f({ min: 30 }), undefined)).toBe('≥ 30');
    expect(valueText(f({ max: 14 }), undefined)).toBe('≤ 14');
    expect(valueText(f({ within: { amount: 5, unit: 'sessions' } }), undefined)).toBe(
      '≤ 5 sessions',
    );
  });
});

describe('chipItems', () => {
  it('joins each filter in force with its served counts, and names an undefined id by itself', () => {
    const items = chipItems(
      [
        { id: 'decision', values: ['QUALIFIED'], active: true },
        { id: 'gone', values: ['a'], active: false },
      ],
      DEFS,
      FACETS,
    );
    expect(items).toEqual([
      {
        id: 'decision',
        label: 'Decision',
        valueText: 'Qualified',
        active: true,
        removes: 5,
        unknown: 3,
      },
      { id: 'gone', label: 'gone', valueText: 'a', active: false },
    ]);
  });
});

describe('recoveryItems', () => {
  it('offers the active filters that remove most, largest first, never a switched-off one', () => {
    const filters: FilterState[] = [
      { id: 'decision', values: ['QUALIFIED'], active: true },
      { id: 'earnings', within: { amount: 5, unit: 'sessions' }, active: true },
    ];
    expect(recoveryItems(filters, DEFS, FACETS)).toEqual([
      { id: 'earnings', label: 'Earnings', gives: 20 },
      { id: 'decision', label: 'Decision', gives: 5 },
    ]);
    expect(
      recoveryItems([{ ...(filters[1] as FilterState), active: false }], DEFS, FACETS),
    ).toEqual([]);
  });
});

describe('groupCounts and countLine', () => {
  it('counts the filters in force per group', () => {
    const counts = groupCounts(
      [
        { id: 'decision', values: ['x'], active: true },
        { id: 'earnings', max: 1, active: true },
      ],
      DEFS,
    );
    expect(counts.get('SETUP')).toBe(1);
    expect(counts.get('COMING_UP')).toBe(1);
    expect(counts.get('TRADEABLE')).toBeUndefined();
  });

  it('writes "N of M" from the served counts', () => {
    expect(countLine(FACETS)).toBe('12 of 340');
    expect(countLine(null)).toBeUndefined();
  });
});
