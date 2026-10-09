import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { SUGGESTIONS, TickerSearch } from './TickerSearch';

const hooks = vi.hoisted(() => ({ useFeatureTable: vi.fn() }));

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureTable: hooks.useFeatureTable,
}));

const rows = [
  { symbol: 'NVDA', name: 'NVIDIA Corp' },
  { symbol: 'NVO', name: 'Novo Nordisk' },
];

beforeEach(() => {
  hooks.useFeatureTable.mockReset();
  hooks.useFeatureTable.mockReturnValue(fakeQuery({ rows }));
});

describe('TickerSearch', () => {
  it('asks the server for a handful of matches once something is typed', async () => {
    render(<TickerSearch onChoose={vi.fn()} />);
    await userEvent.type(screen.getByRole('combobox', { name: 'Search tickers' }), 'nv');
    await waitFor(() => {
      expect(hooks.useFeatureTable).toHaveBeenLastCalledWith(
        { columns: [], filters: { q: 'nv' }, size: SUGGESTIONS },
        true,
      );
    });
    expect(hooks.useFeatureTable).toHaveBeenCalledWith(expect.anything(), false);
  });

  it('lists symbol and name, marks open tickers, and chooses with arrows and Enter', async () => {
    const onChoose = vi.fn();
    const { container } = render(<TickerSearch onChoose={onChoose} chosen={['NVO']} />);
    const box = screen.getByRole('combobox', { name: 'Search tickers' });
    await userEvent.type(box, 'nv');
    await waitFor(() => {
      expect(screen.getAllByRole('option')).toHaveLength(2);
    });
    expect(screen.getByRole('option', { name: /NVO.*open.*Novo Nordisk/ })).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{Enter}');
    expect(onChoose).toHaveBeenCalledWith('NVO');
    expect(box).toHaveValue('');
  });

  it('says when nothing matches and when the search failed', async () => {
    hooks.useFeatureTable.mockReturnValue(fakeQuery({ rows: [] }));
    const { rerender } = render(<TickerSearch onChoose={vi.fn()} />);
    await userEvent.type(screen.getByRole('combobox'), 'zzz');
    expect(await screen.findByText('No ticker matches “zzz”')).toBeInTheDocument();
    hooks.useFeatureTable.mockReturnValue({ ...fakeQuery(undefined), isError: true });
    rerender(<TickerSearch onChoose={vi.fn()} />);
    expect(await screen.findByText('The search failed')).toBeInTheDocument();
  });

  it('focuses on its key from anywhere outside a text field', async () => {
    render(<TickerSearch onChoose={vi.fn()} focusKey="/" />);
    await userEvent.keyboard('/');
    expect(screen.getByRole('combobox')).toHaveFocus();
  });
});
