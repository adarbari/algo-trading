import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { onboardingGuard } from './onboarding';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);
let queryClient: QueryClient;
beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  GQL.mockReset();
});

async function redirected(pathname: string): Promise<string | undefined> {
  try {
    await onboardingGuard({ context: { queryClient }, location: { pathname } });
  } catch (thrown) {
    return (thrown as { options: { to: string } }).options.to;
  }
  return undefined;
}

const answer = (defaultTab: string | null) => ({
  traderPreferences: { defaultTab, watchlist: [] },
});

describe('onboardingGuard', () => {
  it('sends a viewer with no stored start tab to the question', async () => {
    GQL.mockResolvedValue(answer(null));
    expect(await redirected('/ideas')).toBe('/onboarding');
  });

  it('lets a viewer who answered through, and never loops on the question itself', async () => {
    GQL.mockResolvedValue(answer('premium'));
    expect(await redirected('/ideas')).toBeUndefined();
    GQL.mockResolvedValue(answer(null));
    expect(await redirected('/onboarding')).toBeUndefined();
  });

  it('never locks anyone out when the read fails', async () => {
    GQL.mockRejectedValue(new Error('down'));
    expect(await redirected('/ideas')).toBeUndefined();
  });
});
