import { describe, expect, it, vi } from 'vitest';

import { backToEdge, NEW_EDGE, validateReturnSearch } from './return-to-edge';

describe('validateReturnSearch', () => {
  it('keeps the edge to return to and drops anything else', () => {
    expect(validateReturnSearch({ returnTo: 'my_edge' })).toEqual({ returnTo: 'my_edge' });
    expect(validateReturnSearch({ returnTo: '' })).toEqual({});
    expect(validateReturnSearch({ returnTo: 3 })).toEqual({});
    expect(validateReturnSearch({})).toEqual({});
  });
});

describe('backToEdge', () => {
  it("returns to the edge's builder, with the screen just edited or made", () => {
    const navigate = vi.fn();
    backToEdge(navigate as never, 'my_edge', 'momo');
    expect(navigate).toHaveBeenCalledWith({
      to: '/edges/$id/edit',
      params: { id: 'my_edge' },
      search: { screen: 'momo' },
    });
  });

  it('returns to a new edge that is not saved yet', () => {
    const navigate = vi.fn();
    backToEdge(navigate as never, NEW_EDGE);
    expect(navigate).toHaveBeenCalledWith({ to: '/edges/new', search: {} });
  });
});
