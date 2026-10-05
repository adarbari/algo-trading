import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PreviewDiff } from './PreviewDiff';

const state = vi.hoisted(() => ({
  builder: {},
  saved: {},
}));

vi.mock('@/features/screener-builder', () => ({ useScreenerBuilder: () => state.builder }));
vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenTable: () => state.saved,
}));

const row = (symbol: string, decision: string) => ({ symbol, decision });

beforeEach(() => {
  state.saved = {
    data: {
      session: '2026-10-01',
      page: { items: [row('AAPL', 'QUALIFIED'), row('SOXS', 'WATCH')] },
    },
  };
  state.builder = {
    dirty: true,
    preview: {
      data: { session: '2026-10-02', rows: [row('AAPL', 'QUALIFIED'), row('KO', 'WATCH')] },
    },
  };
});

describe('PreviewDiff', () => {
  it('says who would enter and who would leave, against the saved run', () => {
    render(<PreviewDiff id="vrp" />);
    expect(
      screen.getByText(
        'Unsaved changes: preview on 2026-10-02, against the saved run of 2026-10-01',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('+1 enter: KO. -1 leave: SOXS.')).toBeInTheDocument();
  });

  it('offers to review the criteria, and says when nothing would change', async () => {
    const onReview = vi.fn();
    state.builder = {
      dirty: true,
      preview: {
        data: { session: '2026-10-02', rows: [row('AAPL', 'QUALIFIED'), row('SOXS', 'WATCH')] },
      },
    };
    render(<PreviewDiff id="vrp" onReview={onReview} />);
    expect(screen.getByText('The same tickers are picked.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Review criteria' }));
    expect(onReview).toHaveBeenCalled();
  });

  it('shows nothing without unsaved changes, a saved run or a preview', () => {
    state.builder = { ...state.builder, dirty: false };
    const { container, rerender } = render(<PreviewDiff id="vrp" />);
    expect(container).toBeEmptyDOMElement();
    state.builder = { dirty: true, preview: { data: undefined } };
    rerender(<PreviewDiff id="vrp" />);
    expect(container).toBeEmptyDOMElement();
    state.builder = { dirty: true, preview: { data: { session: 'x', rows: [] } } };
    state.saved = { data: undefined };
    rerender(<PreviewDiff id="vrp" />);
    expect(container).toBeEmptyDOMElement();
  });
});
