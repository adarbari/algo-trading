import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TRADES_FIXTURE, UNKNOWN_FIXTURE } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeTrades } from './EdgeTrades';

const hooks = vi.hoisted(() => ({ useEdgeTrades: vi.fn() }));

vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdgeTrades: hooks.useEdgeTrades,
}));
vi.mock('@/entities/availability', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    unknownWord: () => 'Unknown',
    UnknownNote: ({ unknown }: { unknown: { kindText: string } }) => (
      <Text>{unknown.kindText}</Text>
    ),
  };
});
vi.mock('@/features/edge-trades-csv', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    TradesCsvButton: ({ edgeId, period }: { edgeId: string; period: string }) => (
      <Text>{`csv ${edgeId} ${period}`}</Text>
    ),
  };
});
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

stubElementSize();

const last = () => hooks.useEdgeTrades.mock.calls.at(-1)?.[0] as Record<string, unknown>;

beforeEach(() => {
  hooks.useEdgeTrades.mockReset();
  hooks.useEdgeTrades.mockReturnValue(fakeQuery(TRADES_FIXTURE));
});

describe('EdgeTrades', () => {
  it('shows a page of the ledger with the unknown cells in words, not as numbers', async () => {
    const { container } = render(<EdgeTrades edgeId="drift" />);
    const table = screen.getByRole('grid', { name: 'Trade ledger' });
    expect(within(table).getByText('US-AAA')).toBeInTheDocument();
    expect(within(table).getByText('Licensed')).toBeInTheDocument(); // a personal-licence score
    expect(within(table).getAllByText('Not stored').length).toBeGreaterThan(0);
    expect(within(table).getByText('Excluded')).toBeInTheDocument();
    expect(within(table).getByText('No entry bar')).toBeInTheDocument(); // the public reason
    expect(screen.getByText('3 trades')).toBeInTheDocument();
    expect(screen.getByText('help trade_ledger')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('asks the server for another period, another sort and the next page', async () => {
    render(<EdgeTrades edgeId="drift" />);
    expect(last()).toMatchObject({ period: 'ALL', page: 1, sort: 'DECISION', descending: false });
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(last()).toMatchObject({ page: 2 });
    await userEvent.click(screen.getByRole('radio', { name: 'Out-of-sample' }));
    expect(last()).toMatchObject({ period: 'OUT_OF_SAMPLE', page: 1 }); // a new period starts at page 1
    await userEvent.click(within(screen.getByRole('grid')).getByRole('button', { name: /^Rank/ }));
    expect(last()).toMatchObject({ sort: 'RANK', page: 1 });
  });

  it('hands the period shown to the CSV button', async () => {
    render(<EdgeTrades edgeId="drift" />);
    expect(screen.getByText('csv drift ALL')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Live' }));
    expect(screen.getByText('csv drift LIVE')).toBeInTheDocument();
  });

  it('says why there is no ledger, and that a copy hides its out-of-sample trades', () => {
    hooks.useEdgeTrades.mockReturnValue(
      fakeQuery({ ...TRADES_FIXTURE, rows: [], total: 0, unknown: UNKNOWN_FIXTURE }),
    );
    const { rerender } = render(<EdgeTrades edgeId="drift" />);
    expect(screen.getByText('not stored for this run')).toBeInTheDocument();
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
    hooks.useEdgeTrades.mockReturnValue(
      fakeQuery({ ...TRADES_FIXTURE, rows: [], total: 0, oosHidden: true }),
    );
    rerender(<EdgeTrades edgeId="drift" />);
    expect(screen.getByText('Out-of-sample trades hidden')).toBeInTheDocument();
  });

  it('shows loading and failed with a retry', async () => {
    hooks.useEdgeTrades.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<EdgeTrades edgeId="drift" />);
    expect(screen.getByText('Loading the trades')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeTrades.mockReturnValue(failed);
    rerender(<EdgeTrades edgeId="drift" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
