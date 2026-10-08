import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PreviewDiff } from './PreviewDiff';

const state = vi.hoisted(() => ({ builder: {} }));

vi.mock('@/features/screener-builder', () => ({ useScreenerBuilder: () => state.builder }));

const changes = (entered: string[], left: string[]) => ({
  run_id: 'r1',
  session: '2026-10-02',
  entered,
  left,
});

beforeEach(() => {
  state.builder = { dirty: true, preview: { data: { changes: changes(['KO'], ['SOXS']) } } };
});

describe('PreviewDiff', () => {
  it('says who would enter and who would leave, as the server compared them', () => {
    render(<PreviewDiff />);
    expect(
      screen.getByText('Unsaved changes: preview against the saved run of 2026-10-02'),
    ).toBeInTheDocument();
    expect(screen.getByText('+1 enter: KO. -1 leave: SOXS.')).toBeInTheDocument();
  });

  it('says when nothing would change', () => {
    state.builder = { dirty: true, preview: { data: { changes: changes([], []) } } };
    render(<PreviewDiff />);
    expect(screen.getByText('The same tickers are picked.')).toBeInTheDocument();
  });

  it('shows nothing without unsaved changes, a preview or a saved run', () => {
    state.builder = { ...state.builder, dirty: false };
    const { container, rerender } = render(<PreviewDiff />);
    expect(container).toBeEmptyDOMElement();
    state.builder = { dirty: true, preview: { data: undefined } };
    rerender(<PreviewDiff />);
    expect(container).toBeEmptyDOMElement();
    state.builder = { dirty: true, preview: { data: { changes: null } } };
    rerender(<PreviewDiff />);
    expect(container).toBeEmptyDOMElement();
  });
});
