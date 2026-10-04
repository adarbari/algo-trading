import { ToastProvider } from '@algotrade/ui';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { IdeasResponse, ScreenerSummary } from '@/entities/idea';
import { api, queryKeys } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ScreenerPriorityList } from './ScreenerPriorityList';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { PUT: vi.fn() } };
});

const PUT = vi.mocked(api.PUT);

const screener = (id: string, qualified: number): ScreenerSummary => ({
  id,
  name: id,
  user: 'abhinav',
  version: 1,
  qualified,
  top: [{ symbol: 'AAPL', score: 84 }],
});
const SCREENERS = [screener('vrp', 3), screener('liq', 5)];

const cached: IdeasResponse = {
  session: '2026-10-02',
  priority: ['vrp', 'liq'],
  total: 0,
  screeners: [],
  items: [],
};
const key = queryKeys.ideas.top(200);

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.setQueryData(key, cached);
  const view = render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <ScreenerPriorityList screeners={SCREENERS} />
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
    expect(screen.getAllByText('qualified')).toHaveLength(2);
    await expectNoA11yViolations(container);
  });

  it('saves the new order at once (optimistic) and refetches when settled', async () => {
    let resolve: (value: unknown) => void = () => undefined;
    PUT.mockReturnValue(new Promise((r) => (resolve = r)) as never);
    const { client } = setup();
    await moveFirstDown();
    expect(PUT).toHaveBeenCalledWith('/preferences/ideas', { body: { priority: ['liq', 'vrp'] } });
    await waitFor(() => {
      expect(client.getQueryData<IdeasResponse>(key)?.priority).toEqual(['liq', 'vrp']);
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
    expect(client.getQueryData<IdeasResponse>(key)?.priority).toEqual(['vrp', 'liq']);
  });
});
