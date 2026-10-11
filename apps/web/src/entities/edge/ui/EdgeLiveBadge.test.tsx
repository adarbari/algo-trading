import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { EdgeLiveBadge } from './EdgeLiveBadge';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);
const state = (edgeId: string, s: string) => ({
  edgeId,
  name: edgeId,
  state: s,
  closed: 20,
  winRate: 0.2,
  headline: '',
  followed: true,
});

function show(edgeId: string, states: ReturnType<typeof state>[]) {
  GQL.mockResolvedValue({ edgeDesk: { liveStates: states } });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <EdgeLiveBadge edgeId={edgeId} help={<span>help live_state</span>} />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  GQL.mockReset();
});

describe('EdgeLiveBadge', () => {
  it('shows the badge when the edge is below its usual range', async () => {
    show('drift', [state('drift', 'below')]);
    expect(await screen.findByText('Below range')).toBeVisible();
    expect(screen.getByText('help live_state')).toBeVisible();
  });

  it('shows nothing for an edge on track, above range or without a live state', async () => {
    const client = show('drift', [state('drift', 'on_track'), state('other', 'below')]);
    await vi.waitFor(() => {
      expect(client.isFetching()).toBe(0);
    });
    expect(screen.queryByText('Below range')).not.toBeInTheDocument();
    expect(screen.queryByText('On track')).not.toBeInTheDocument();
    expect(screen.queryByText('help live_state')).not.toBeInTheDocument();
  });
});
