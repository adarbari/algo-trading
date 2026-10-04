import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { NewScreenerForm } from './NewScreenerForm';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn(), PUT: vi.fn() } };
});

const GET = vi.mocked(api.GET);
const PUT = vi.mocked(api.PUT);

beforeEach(() => {
  GET.mockReset();
  PUT.mockReset();
  GET.mockResolvedValue({
    data: [
      { config_id: 'vrp', scope: 'site', kind: 'screener', selection: 'vrp_universe' },
      { config_id: 'taken', scope: 'u', kind: 'screener', selection: 'inline' },
    ],
    response: new Response(null, { status: 200 }),
  });
  PUT.mockResolvedValue({
    data: { screener_id: 'mine', document: {} },
    response: new Response(null, { status: 200 }),
  });
});

function setup() {
  const onCreated = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <TestQueryProvider>
      <NewScreenerForm onCreated={onCreated} onCancel={onCancel} />
    </TestQueryProvider>,
  );
  return { onCreated, onCancel, ...view };
}

describe('NewScreenerForm', () => {
  it('saves a blank draft over the chosen universe and opens it', async () => {
    const { onCreated, container } = setup();
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'mine');
    expect(await screen.findByRole('combobox', { name: 'Universe' })).toHaveValue('vrp_universe');
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole('button', { name: 'Create draft' }));
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith('mine');
    });
    expect(PUT).toHaveBeenCalledWith('/screeners/{screener_id}/draft', {
      params: { path: { screener_id: 'mine' } },
      body: {
        document: {
          id: 'mine',
          kind: 'screener',
          impl: 'rules',
          selection: 'vrp_universe',
          criteria: {},
        },
      },
    });
  });

  it('refuses an invalid or taken name before saving', async () => {
    setup();
    const name = screen.getByRole('textbox', { name: 'Name' });
    await userEvent.type(name, 'Bad Name');
    expect(screen.getByText('Use 1-64 of a-z, 0-9, _ and -.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create draft' })).toBeDisabled();
    await userEvent.clear(name);
    await userEvent.type(name, 'taken');
    expect(
      await screen.findByText('A screener with this name already exists.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create draft' })).toBeDisabled();
    expect(PUT).not.toHaveBeenCalled();
  });

  it('falls back to the site universe when no screener names one', async () => {
    GET.mockResolvedValue({ data: [], response: new Response(null, { status: 200 }) });
    setup();
    expect(await screen.findByRole('combobox', { name: 'Universe' })).toHaveValue(
      'liquid_optionable',
    );
  });

  it('cancels', async () => {
    const { onCancel } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
  });
});
