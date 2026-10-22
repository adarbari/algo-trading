import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  AuthFailure,
  currentSession,
  gql,
  signInWithPassword,
  signOutSession,
  subscribeSession,
} from '@/shared/api';

import { useSession, useSignIn, useSignOut } from './session';
import { viewerKey } from './viewer';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    gql: vi.fn(),
    currentSession: vi.fn(),
    subscribeSession: vi.fn(),
    signInWithPassword: vi.fn(),
    signOutSession: vi.fn(),
  };
});

const GQL = vi.mocked(gql);
const TRADER = { id: 'ann', name: 'Ann', role: 'trader', workspaces: ['trader'] };
let client: QueryClient;

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
);

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(signInWithPassword).mockResolvedValue(undefined);
  vi.mocked(signOutSession).mockResolvedValue(undefined);
});

describe('useSession', () => {
  it('reads the stored session, then follows changes', async () => {
    vi.mocked(currentSession).mockResolvedValue({ email: 'a@b.co' });
    let emit: (s: { email: string } | null) => void = () => undefined;
    vi.mocked(subscribeSession).mockImplementation((listener) => {
      emit = listener;
      return () => undefined;
    });
    const { result } = renderHook(() => useSession());
    expect(result.current.ready).toBe(false);
    await waitFor(() => {
      expect(result.current).toEqual({ ready: true, session: { email: 'a@b.co' } });
    });
    act(() => {
      emit(null);
    });
    expect(result.current).toEqual({ ready: true, session: null });
  });
});

describe('useSignIn', () => {
  it('signs in, confirms the API knows the user and caches the viewer', async () => {
    GQL.mockResolvedValue({ viewer: TRADER });
    const { result } = renderHook(() => useSignIn(), { wrapper });
    let viewer: unknown;
    await act(async () => {
      viewer = await result.current.signIn('a@b.co', 'pw');
    });
    expect(signInWithPassword).toHaveBeenCalledWith('a@b.co', 'pw');
    expect(viewer).toEqual(TRADER);
    expect(client.getQueryData(viewerKey)).toEqual(TRADER);
    expect(result.current.error).toBeUndefined();
  });

  it('says wrong credentials in plain words and stays signed out', async () => {
    vi.mocked(signInWithPassword).mockRejectedValue(
      new AuthFailure('Invalid login credentials', 'invalid_credentials'),
    );
    const { result } = renderHook(() => useSignIn(), { wrapper });
    let viewer: unknown = 'unset';
    await act(async () => {
      viewer = await result.current.signIn('a@b.co', 'bad');
    });
    expect(viewer).toBeNull();
    await waitFor(() => {
      expect(result.current.error).toBe('Wrong email or password.');
    });
    expect(GQL).not.toHaveBeenCalled();
  });

  it('signs out again and says "not registered" when the API answers 403', async () => {
    GQL.mockRejectedValue(new ApiError(403, 'Forbidden'));
    const { result } = renderHook(() => useSignIn(), { wrapper });
    await act(async () => {
      await result.current.signIn('a@b.co', 'pw');
    });
    expect(signOutSession).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(result.current.error).toBe(
        'Your account is not registered for this app; ask an admin to add you.',
      );
    });
  });

  it('clears the error on reset (the page calls it when the user edits)', async () => {
    vi.mocked(signInWithPassword).mockRejectedValue(new AuthFailure('x', 'invalid_credentials'));
    const { result } = renderHook(() => useSignIn(), { wrapper });
    await act(async () => {
      await result.current.signIn('a@b.co', 'bad');
    });
    await waitFor(() => {
      expect(result.current.error).toBeDefined();
    });
    act(() => {
      result.current.reset();
    });
    await waitFor(() => {
      expect(result.current.error).toBeUndefined();
    });
  });
});

describe('useSignOut', () => {
  it('ends the session, forgets the cache and makes the viewer null', async () => {
    client.setQueryData(viewerKey, TRADER);
    client.setQueryData(['gql', 'IdeasPage', {}], { secret: 1 });
    const { result } = renderHook(() => useSignOut(), { wrapper });
    await act(async () => {
      await result.current();
    });
    expect(signOutSession).toHaveBeenCalledTimes(1);
    expect(client.getQueryData(viewerKey)).toBeNull();
    expect(client.getQueryData(['gql', 'IdeasPage', {}])).toBeUndefined();
  });
});
