import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';

import { RemoveScopeNameDialog } from './RemoveScopeNameDialog';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { PUT: vi.fn(), DELETE: vi.fn() } };
});

const DELETE = vi.mocked(api.DELETE);

beforeEach(() => {
  DELETE.mockReset();
});

const setup = (onOpenChange = vi.fn()) => {
  render(
    <TestQueryProvider>
      <RemoveScopeNameDialog symbol="AAPL" open onOpenChange={onOpenChange} />
    </TestQueryProvider>,
  );
  return onOpenChange;
};

describe('RemoveScopeNameDialog', () => {
  it('removes with the note as a query parameter and closes', async () => {
    DELETE.mockResolvedValue({
      data: { symbol: 'AAPL', listed: false, changed: true },
      response: new Response(null, { status: 200 }),
    });
    const onOpenChange = setup();
    await userEvent.type(screen.getByRole('textbox', { name: /Note/ }), 'delisted');
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }));
    await vi.waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
    expect(DELETE).toHaveBeenCalledWith('/admin/events/scope/{symbol}', {
      params: { path: { symbol: 'AAPL' }, query: { note: 'delisted' } },
    });
  });

  it('sends no query without a note and shows a refusal', async () => {
    DELETE.mockResolvedValue({
      error: { detail: 'admin only' },
      response: new Response(null, { status: 403 }),
    });
    const onOpenChange = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }));
    expect(await screen.findByText('admin only')).toBeInTheDocument();
    expect(DELETE).toHaveBeenCalledWith('/admin/events/scope/{symbol}', {
      params: { path: { symbol: 'AAPL' } },
    });
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});
