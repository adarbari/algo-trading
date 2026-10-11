import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TradesCsvButton } from './TradesCsvButton';

const hooks = vi.hoisted(() => ({ useTradesCsv: vi.fn(), mutate: vi.fn() }));

vi.mock('../api/use-trades-csv', () => ({ useTradesCsv: hooks.useTradesCsv }));

beforeEach(() => {
  hooks.mutate.mockReset();
  hooks.useTradesCsv.mockReturnValue({ mutate: hooks.mutate, isPending: false, isError: false });
});

describe('TradesCsvButton', () => {
  it('saves the period shown, and says when the file could not be saved', async () => {
    const { rerender } = render(<TradesCsvButton edgeId="drift" period="LIVE" />);
    await userEvent.click(screen.getByRole('button', { name: 'CSV' }));
    expect(hooks.mutate).toHaveBeenCalledWith('LIVE');
    hooks.useTradesCsv.mockReturnValue({ mutate: hooks.mutate, isPending: false, isError: true });
    rerender(<TradesCsvButton edgeId="drift" period="LIVE" />);
    expect(screen.getByText('The file could not be saved.')).toBeInTheDocument();
  });
});
