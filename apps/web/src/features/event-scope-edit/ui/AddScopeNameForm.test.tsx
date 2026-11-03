import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { AddScopeNameForm } from './AddScopeNameForm';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { PUT: vi.fn(), DELETE: vi.fn() } };
});

const PUT = vi.mocked(api.PUT);

beforeEach(() => {
  PUT.mockReset();
});

const setup = () =>
  render(
    <TestQueryProvider>
      <AddScopeNameForm />
    </TestQueryProvider>,
  );

describe('AddScopeNameForm', () => {
  it('adds the ticker with its note, then clears the form', async () => {
    PUT.mockResolvedValue({
      data: { symbol: 'NVDA', listed: true, changed: true },
      response: new Response(null, { status: 200 }),
    });
    const { container } = setup();
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();
    await userEvent.type(screen.getByRole('textbox', { name: /Ticker/ }), 'nvda');
    await userEvent.type(screen.getByRole('textbox', { name: /Note/ }), 'owner list');
    await userEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(await screen.findByText('was added.')).toBeInTheDocument();
    expect(PUT).toHaveBeenCalledWith('/admin/events/scope/{symbol}', {
      params: { path: { symbol: 'nvda' } },
      body: { note: 'owner list' },
    });
    expect(screen.getByRole('textbox', { name: /Ticker/ })).toHaveValue('');
    await expectNoA11yViolations(container);
  });

  it('shows the server detail when the ticker does not resolve and keeps what was typed', async () => {
    PUT.mockResolvedValue({
      error: { detail: 'ZZZZ is not in the reference snapshot' },
      response: new Response(null, { status: 404 }),
    } as never);
    setup();
    await userEvent.type(screen.getByRole('textbox', { name: /Ticker/ }), 'ZZZZ');
    await userEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(await screen.findByText('ZZZZ is not in the reference snapshot')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Ticker/ })).toHaveValue('ZZZZ');
  });

  it('says a repeat was already listed', async () => {
    PUT.mockResolvedValue({
      data: { symbol: 'AAPL', listed: true, changed: false },
      response: new Response(null, { status: 200 }),
    });
    setup();
    await userEvent.type(screen.getByRole('textbox', { name: /Ticker/ }), 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(await screen.findByText('was already listed.')).toBeInTheDocument();
  });
});
