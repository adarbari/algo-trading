import { ToastProvider } from '@algotrade/ui';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { IDEAS_OPERATION, type IdeasResponse, type ScreenerSummary } from '@/entities/idea';
import { api, queryKeys } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ScreenerPriorityList } from './ScreenerPriorityList';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { PUT: vi.fn() } };
});

const PUT = vi.mocked(api.PUT);

const screener = (id: string, picked: number): ScreenerSummary => ({
  id,
  name: id,
  owner: 'abhinav',
  version: 1,
  picked,
  notRun: null,
  top: [{ symbol: 'AAPL', score: 84 }],
});
const SCREENERS = [screener('vrp', 3), screener('liq', 5)];

const served = (id: string) => ({
  screener: { id, name: id, owner: 'abhinav', version: 1 },
  run: { runId: `run-${id}`, configVersion: 1, paused: 0 },
  notRun: null,
  picked: 1,
  top: [],
});
const cached: IdeasResponse = {
  ideas: {
    session: '2026-10-02',
    priority: ['vrp', 'liq'],
    total: 0,
    pausedTotal: 0,
    paused: [],
    screeners: [served('vrp'), served('liq')],
    items: [],
  },
};
const key = queryKeys.gql(IDEAS_OPERATION, { limit: 200, names: [] });
const priorityOf = (data: IdeasResponse | undefined) => data?.ideas?.priority;
const orderOf = (data: IdeasResponse | undefined) =>
  data?.ideas?.screeners.map((s) => s.screener.id);

function setup(onOpenScreener?: (id: string) => void) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.setQueryData(key, cached);
  const view = render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <ScreenerPriorityList
          screeners={SCREENERS}
          {...(onOpenScreener ? { onOpenScreener } : {})}
        />
      </QueryClientProvider>
    </ToastProvider>,
  );
  return { client, ...view };
}

async function moveFirstDown() {
  const user = userEvent.setup();
  await user.tab();
  await user.keyboard(' {ArrowDown} ');
}

beforeEach(() => {
  PUT.mockReset();
});

describe('ScreenerPriorityList', () => {
  it('shows rank, name and count, with no accessibility violations', async () => {
    PUT.mockResolvedValue({} as never);
    const { container } = setup();
    expect(screen.getByRole('list', { name: 'Screener priority' })).toBeInTheDocument();
    expect(screen.getByText('vrp')).toBeInTheDocument();
    expect(screen.getAllByText('picked')).toHaveLength(2);
    await expectNoA11yViolations(container);
  });

  it("opens a screener's results from its name when given the callback", async () => {
    const onOpenScreener = vi.fn();
    setup(onOpenScreener);
    await userEvent.setup().click(screen.getByRole('button', { name: 'liq' }));
    expect(onOpenScreener).toHaveBeenCalledWith('liq');
  });

  it('saves the new order at once (optimistic) and refetches when settled', async () => {
    let resolve: (value: unknown) => void = () => undefined;
    PUT.mockReturnValue(new Promise((r) => (resolve = r)) as never);
    const { client } = setup();
    await moveFirstDown();
    expect(PUT).toHaveBeenCalledWith('/preferences/ideas', { body: { priority: ['liq', 'vrp'] } });
    await waitFor(() => {
      expect(priorityOf(client.getQueryData<IdeasResponse>(key))).toEqual(['liq', 'vrp']);
      expect(orderOf(client.getQueryData<IdeasResponse>(key))).toEqual(['liq', 'vrp']);
    });
    resolve({
      data: { priority: ['liq', 'vrp'] },
      response: new Response(null, { status: 200 }),
    });
    await waitFor(() => {
      expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    });
  });

  it('rolls back and toasts when the save fails', async () => {
    PUT.mockResolvedValue({
      error: { detail: 'down' },
      response: new Response(null, { status: 500 }),
    } as never);
    const { client } = setup();
    await moveFirstDown();
    expect(await screen.findByText('Could not save the screener order')).toBeInTheDocument();
    expect(priorityOf(client.getQueryData<IdeasResponse>(key))).toEqual(['vrp', 'liq']);
  });
});
