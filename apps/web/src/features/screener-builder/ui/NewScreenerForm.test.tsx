import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { NewScreenerForm } from './NewScreenerForm';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { PUT: vi.fn() }, gql: vi.fn() };
});

const GQL = vi.mocked(gql);
const PUT = vi.mocked(api.PUT);

beforeEach(() => {
  GQL.mockReset();
  PUT.mockReset();
  // The screener configs (a site preset, one of the user's) and the user's own screens.
  GQL.mockImplementation((document: unknown) =>
    Promise.resolve(
      String(document).includes('query MyScreens')
        ? { myScreens: [{ screenerId: 'drafted', status: 'DRAFT' }] }
        : {
            configs: [
              { configId: 'vrp', scope: 'site', kind: 'screener', selection: 'vrp_universe' },
              { configId: 'taken', scope: 'u', kind: 'screener', selection: 'inline' },
            ],
          },
    ),
  );
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
  it('saves a draft with the base gates and opens it', async () => {
    const { onCreated, container } = setup();
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'mine');
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
          criteria: {
            security_type: {
              field: 'instrument.security_type',
              op: 'in',
              value: ['COMMON_STOCK', 'ADR', 'ETF'],
            },
            status: { field: 'instrument.status', op: 'eq', value: 'ACTIVE' },
            optionable: { field: 'instrument.optionable', op: 'eq', value: true },
          },
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
    await userEvent.clear(name);
    await userEvent.type(name, 'drafted');
    expect(
      await screen.findByText('A screener with this name already exists.'),
    ).toBeInTheDocument();
    expect(PUT).not.toHaveBeenCalled();
  });

  it('cancels', async () => {
    const { onCancel } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
  });
});
