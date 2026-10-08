import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Text } from '@algotrade/ui';

import { api, gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { EvaluationSplitForm } from './EvaluationSplitForm';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { PUT: vi.fn() }, gql: vi.fn() };
});

const PUT = vi.mocked(api.PUT);
const GQL = vi.mocked(gql);

const read = (splitFrom: string | null) => ({
  evaluationSplit: {
    splitFrom,
    latestSession: '2026-09-30',
    frozenPeriods: [{ edgeId: 'momentum_12_1', frozenFrom: '2026-06-01' }],
  },
});

const setup = () =>
  render(
    <TestQueryProvider>
      <EvaluationSplitForm renderTermHelp={(term) => <Text>{`help ${term}`}</Text>} />
    </TestQueryProvider>,
  );

beforeEach(() => {
  PUT.mockReset();
  GQL.mockReset();
});

describe('EvaluationSplitForm', () => {
  it('shows a loading panel, then an error banner when the read fails', async () => {
    GQL.mockRejectedValue(new Error('boom'));
    setup();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
    expect(await screen.findByText('Could not load your split')).toBeInTheDocument();
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('shows the site frozen period, no personal split, and the exploratory help', async () => {
    GQL.mockResolvedValue(read(null));
    const { baseElement } = setup();
    expect(await screen.findByText('momentum_12_1')).toBeInTheDocument();
    expect(screen.getByText('2026-06-01')).toBeInTheDocument();
    expect(screen.getByText(/None: each frozen period/)).toBeInTheDocument();
    expect(screen.getByText('help exploratory')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    await expectNoA11yViolations(baseElement);
  });

  it('saves a date, then says the results are exploratory and from evaluate-edges', async () => {
    GQL.mockResolvedValue(read(null));
    PUT.mockResolvedValue({ data: { split_from: '2026-04-01' }, response: new Response() });
    setup();
    await userEvent.type(await screen.findByLabelText('Test slice starts'), '2026-04-01');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledWith('/evaluation/split', { body: { split_from: '2026-04-01' } });
    });
    expect(await screen.findByText(/labelled EXPLORATORY.*evaluate-edges/)).toBeInTheDocument();
  });

  it('refuses a malformed or later-than-stored date before any request', async () => {
    GQL.mockResolvedValue(read(null));
    setup();
    const input = await screen.findByLabelText('Test slice starts');
    await userEvent.type(input, '04/01/2026');
    expect(screen.getByText('Use the form 2026-04-01.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    await userEvent.clear(input);
    await userEvent.type(input, '2026-10-01');
    expect(screen.getByText('No stored session after 2026-09-30.')).toBeInTheDocument();
    expect(PUT).not.toHaveBeenCalled();
  });

  it('clears a saved split', async () => {
    GQL.mockResolvedValue(read('2026-04-01'));
    PUT.mockResolvedValue({ data: { split_from: null }, response: new Response() });
    setup();
    expect(await screen.findByText('2026-04-01')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledWith('/evaluation/split', { body: { split_from: null } });
    });
    expect(await screen.findByText(/Cleared/)).toBeInTheDocument();
  });

  it("shows the API's refusal as the field's error", async () => {
    GQL.mockResolvedValue(read(null));
    PUT.mockResolvedValue({
      error: { detail: 'split_from 2026-01-01: expected a stored session' } as never,
      response: new Response(null, { status: 400, statusText: 'Bad Request' }),
    });
    setup();
    await userEvent.type(await screen.findByLabelText('Test slice starts'), '2026-01-01');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(/expected a stored session/)).toBeInTheDocument();
  });
});
