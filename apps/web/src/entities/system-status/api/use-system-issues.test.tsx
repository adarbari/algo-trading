import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { gql } from '@/shared/api';

import { useSystemIssues } from './use-system-issues';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const SCREENS = {
  session: { date: '2026-10-08' },
  screeners: [{ id: 'a', name: 'A', notRun: { code: 'NOT_RUN', kindText: 'Not run' } }],
};
const NIGHTLY = {
  nightlyRuns: [
    {
      runId: 'r1',
      session: '2026-10-08',
      status: 'FAILED',
      problems: [],
      steps: [],
    },
  ],
};
/** What the API answers: the admin-only fields are skipped (`@include`) unless `admin`. */
const answer = (variables: unknown) =>
  Promise.resolve((variables as { admin: boolean }).admin ? { ...SCREENS, ...NIGHTLY } : SCREENS);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-08T12:00:00Z'));
  GQL.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useSystemIssues', () => {
  it('reads only the screeners for a trader (the nightly run is admin-only)', async () => {
    GQL.mockImplementation((_doc, variables) => answer(variables));
    const { result } = renderHook(() => useSystemIssues(false), { wrapper });
    await waitFor(() => {
      expect(result.current.issues).toHaveLength(1);
    });
    expect(GQL).toHaveBeenCalledOnce();
    expect(result.current.issues[0]?.id).toBe('screen:2026-10-08:a');
  });

  it('adds the failed nightly run for an admin, ahead of the warnings', async () => {
    GQL.mockImplementation((_doc, variables) => answer(variables));
    const { result } = renderHook(() => useSystemIssues(true), { wrapper });
    await waitFor(() => {
      expect(result.current.issues).toHaveLength(2);
    });
    expect(GQL).toHaveBeenCalledOnce();
    expect(result.current.issues.map((i) => i.severity)).toEqual(['failing', 'warning']);
  });

  it('asks only for what the strip shows, in one operation: no picks, a one-session grid', async () => {
    // The ranked ideas and a ten-session grid cost the API 6 s of reads on every page; four
    // requests (screens, nightly, grid, viewer) were three more round trips than needed.
    GQL.mockImplementation((_doc, variables) => answer(variables));
    renderHook(() => useSystemIssues(true), { wrapper });
    await waitFor(() => {
      expect(GQL).toHaveBeenCalledOnce();
    });
    const [document, variables] = GQL.mock.calls[0] ?? [];
    const text = String(document);
    expect(text).toContain('query StatusStrip');
    expect(text).not.toContain('ideas');
    expect(text).toContain('nightlyRuns(limit: 1) @include(if: $admin)');
    expect(text).toContain('completeness(sessions: 1) @include(if: $admin)');
    expect(variables).toEqual({ admin: true });
  });

  it('adds no issue while a read fails', async () => {
    GQL.mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useSystemIssues(true), { wrapper });
    await waitFor(() => {
      expect(GQL).toHaveBeenCalled();
    });
    expect(result.current.issues).toEqual([]);
  });
});

describe('the session notice of useSystemIssues', () => {
  it('hands over the newer incomplete session from the same read', async () => {
    const newer = { date: '2026-10-09', state: 'FAILED_RETRYING' };
    GQL.mockResolvedValue({ ...SCREENS, session: { date: '2026-10-01', newer } });
    const { result } = renderHook(() => useSystemIssues(false), { wrapper });
    await waitFor(() => {
      expect(result.current.notice).toMatchObject({ date: '2026-10-01', newer });
    });
    expect(GQL).toHaveBeenCalledOnce(); // one request for the strip and the notice
  });

  it('is null when the served session is the newest', async () => {
    GQL.mockImplementation((_doc, variables) => answer(variables));
    const { result } = renderHook(() => useSystemIssues(false), { wrapper });
    await waitFor(() => {
      expect(GQL).toHaveBeenCalled();
    });
    expect(result.current.notice).toBeNull();
  });
});
