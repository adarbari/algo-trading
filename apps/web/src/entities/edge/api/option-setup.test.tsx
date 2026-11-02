import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { OPTION_SETUP_FIXTURE } from '../model/fixtures-option';
import { isOptionSetup } from '../model/option-setup';
import { useOptionSetup } from './option-setup';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  GQL.mockReset();
});

describe('the option setup read', () => {
  it('reads one setup by id and serves it as sent', async () => {
    GQL.mockResolvedValue({ edgeOptionSetup: OPTION_SETUP_FIXTURE });
    const { result } = renderHook(() => useOptionSetup('put_write_weekly'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query OptionSetup');
    expect(GQL.mock.calls[0]?.[1]).toEqual({ id: 'put_write_weekly' });
    expect(result.current.data).toEqual(OPTION_SETUP_FIXTURE);
    expect(isOptionSetup(result.current.data)).toBe(true);
  });

  it('is not an option setup when there is no such edge or it holds shares', () => {
    expect(isOptionSetup(null)).toBe(false);
    expect(isOptionSetup({ positionKind: 'shares' })).toBe(false);
  });
});
