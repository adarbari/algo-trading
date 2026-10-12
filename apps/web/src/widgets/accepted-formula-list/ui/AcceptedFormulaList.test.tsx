import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FORMULAS_FIXTURE } from '@/entities/accepted-formula';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { AcceptedFormulaList } from './AcceptedFormulaList';

const hooks = vi.hoisted(() => ({ useAcceptedFormulas: vi.fn() }));
vi.mock('@/entities/accepted-formula', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useAcceptedFormulas: hooks.useAcceptedFormulas,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text>,
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
  };
});

stubElementSize();

beforeEach(() => {
  hooks.useAcceptedFormulas.mockReturnValue(fakeQuery(FORMULAS_FIXTURE));
});

describe('AcceptedFormulaList', () => {
  it('lists one row per formula in the served order with counts, the duplicate and the backlog match', async () => {
    const { container } = render(<AcceptedFormulaList />);
    const table = screen.getByRole('table', { name: 'Accepted formulas' });
    const first = within(table).getByRole('row', { name: /close\/sma_20 - 1/ });
    expect(within(first).getByText('3')).toBeInTheDocument();
    expect(within(first).getByText('4')).toBeInTheDocument();
    expect(within(first).queryByText('DUPLICATE')).not.toBeInTheDocument();
    const dup = within(table).getByRole('row', { name: /high - low/ });
    expect(within(dup).getByText('DUPLICATE')).toBeInTheDocument();
    expect(within(dup).getByRole('link', { name: 'rollup.momentum@v1.rsi_14' })).toHaveAttribute(
      'href',
      '/guide/fields/rollup.momentum%40v1.rsi_14',
    );
    expect(within(dup).getByText('day_range')).toBeInTheDocument();
    expect(screen.getByText('help accepted_formula')).toBeInTheDocument();
    expect(screen.getByText('help read_feature_requests')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows nothing for a backlog match that is not exact', () => {
    render(<AcceptedFormulaList />);
    const row = screen.getByRole('row', { name: /volume \/ avg_volume_20/ });
    expect(within(row).queryByText('day_range')).not.toBeInTheDocument();
  });

  it('opens a row to its canonical form and fingerprint', async () => {
    render(<AcceptedFormulaList />);
    expect(screen.queryByText('Canonical form')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /close\/sma_20 - 1/ }));
    expect(screen.getByText('Canonical form')).toBeInTheDocument();
    expect(screen.getByText('(close / sma_20) - 1')).toBeInTheDocument();
    expect(screen.getByText('a1b2c3d4e5f6')).toBeInTheDocument();
  });

  it('shows the loading, error and empty states', () => {
    hooks.useAcceptedFormulas.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<AcceptedFormulaList />);
    expect(screen.getByText('Loading accepted formulas…')).toBeInTheDocument();
    hooks.useAcceptedFormulas.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<AcceptedFormulaList />);
    expect(screen.getByText('The accepted formulas failed to load.')).toBeInTheDocument();
    hooks.useAcceptedFormulas.mockReturnValue(fakeQuery({ ...FORMULAS_FIXTURE, rows: [] }));
    rerender(<AcceptedFormulaList />);
    expect(screen.getByText('No formula has been accepted.')).toBeInTheDocument();
  });
});
