import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, gql } from '@/shared/api';

import { readDeviceTheme } from '../model/theme';

import { useSaveTheme, useTheme } from './appearance';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn(), api: { PUT: vi.fn() } };
});

const GQL = vi.mocked(gql);
const PUT = vi.mocked(api.PUT);

afterEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { wrapper };
}

describe('the stored theme', () => {
  it('is the answer of Query.appearance, copied to this device', async () => {
    GQL.mockResolvedValue({ appearance: { theme: 'light' } });
    const { wrapper } = setup();
    const { result } = renderHook(() => useTheme(true), { wrapper });
    await waitFor(() => {
      expect(result.current).toBe('light');
    });
    expect(String(GQL.mock.calls[0]?.[0])).toContain('query Appearance');
    expect(readDeviceTheme()).toBe('light');
  });

  it('is undefined, and asks nothing, until enabled or for an unknown value', async () => {
    const { wrapper } = setup();
    const off = renderHook(() => useTheme(false), { wrapper });
    expect(off.result.current).toBeUndefined();
    expect(GQL).not.toHaveBeenCalled();
    GQL.mockResolvedValue({ appearance: { theme: 'sepia' } });
    const odd = renderHook(() => useTheme(true), { wrapper });
    await waitFor(() => {
      expect(GQL).toHaveBeenCalled();
    });
    expect(odd.result.current).toBeUndefined();
    expect(readDeviceTheme()).toBeUndefined();
  });
});

describe('saving the theme', () => {
  it('shows the choice at once and writes it through REST', async () => {
    GQL.mockResolvedValue({ appearance: { theme: 'system' } });
    PUT.mockResolvedValue({ data: { theme: 'dark' }, response: new Response() });
    const { wrapper } = setup();
    const { result } = renderHook(() => ({ theme: useTheme(true), save: useSaveTheme() }), {
      wrapper,
    });
    await waitFor(() => {
      expect(result.current.theme).toBe('system');
    });
    await act(async () => {
      await result.current.save.mutateAsync('dark');
    });
    expect(PUT).toHaveBeenCalledWith('/preferences/appearance', { body: { theme: 'dark' } });
    await waitFor(() => {
      expect(result.current.theme).toBe('dark');
    });
    expect(readDeviceTheme()).toBe('dark');
  });
});
