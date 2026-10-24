import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useFilterState } from './use-filter-state';

function setup(f: string | undefined) {
  const onChange = vi.fn();
  const { result } = renderHook(() => useFilterState(f, onChange));
  return { result, onChange };
}

describe('useFilterState', () => {
  it('reads the filters from f', () => {
    const { result } = setup('a:x,y;!b:1..2');
    expect(result.current.filters.map((x) => [x.id, x.active])).toEqual([
      ['a', true],
      ['b', false],
    ]);
  });

  it('clears one end of a range when the patch leaves it undefined', () => {
    const { result, onChange } = setup('r:5..10');
    act(() => {
      result.current.set('r', { min: undefined, max: 10 });
    });
    expect(onChange).toHaveBeenLastCalledWith('r:..10');
  });

  it('sets, adds, toggles, removes and clears through onChange', () => {
    const { result, onChange } = setup('a:x;b:1..2');
    act(() => {
      result.current.set('a', { values: ['x', 'y'] });
    });
    expect(onChange).toHaveBeenLastCalledWith('a:x,y;b:1..2');
    act(() => {
      result.current.set('c', { within: { amount: 5, unit: 'sessions' } });
    });
    expect(onChange).toHaveBeenLastCalledWith('a:x;b:1..2;c:..5s');
    act(() => {
      result.current.set('b', { max: 9 });
    });
    expect(onChange).toHaveBeenLastCalledWith('a:x;b:1..9');
    act(() => {
      result.current.set('b', { within: { amount: 2, unit: 'days' } });
    });
    expect(onChange).toHaveBeenLastCalledWith('a:x;b:..2d');
    act(() => {
      result.current.toggle('a');
    });
    expect(onChange).toHaveBeenLastCalledWith('!a:x;b:1..2');
    act(() => {
      result.current.remove('a');
    });
    expect(onChange).toHaveBeenLastCalledWith('b:1..2');
    act(() => {
      result.current.clear();
    });
    expect(onChange).toHaveBeenLastCalledWith(undefined);
  });
});
