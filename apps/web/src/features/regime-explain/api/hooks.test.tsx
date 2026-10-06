import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';

import { useExplainAvailable, useExplainRegime } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn() } };
});

const POST = vi.mocked(api.POST);

function wrapper({ children }: { children: ReactNode }) {
  return <TestQueryProvider>{children}</TestQueryProvider>;
}

const refusal = (status: number, detail: string) => ({
  error: { detail },
  response: new Response(null, { status }),
});

beforeEach(() => {
  POST.mockReset();
});

describe('useExplainAvailable', () => {
  it('probes with an empty body: 400 means a model is configured', async () => {
    POST.mockResolvedValue(refusal(400, 'ask one of question or card'));
    const { result } = renderHook(() => useExplainAvailable(), { wrapper });
    await waitFor(() => {
      expect(result.current.data).toBe(true);
    });
    expect(POST).toHaveBeenCalledWith('/regime/explain', {
      body: { question: null, card: null },
    });
  });

  it('503 means no text model: unavailable', async () => {
    POST.mockResolvedValue(refusal(503, 'the text model is off'));
    const { result } = renderHook(() => useExplainAvailable(), { wrapper });
    await waitFor(() => {
      expect(result.current.data).toBe(false);
    });
  });

  it('any other failure is an error (the button stays hidden)', async () => {
    POST.mockResolvedValue(refusal(500, 'boom'));
    const { result } = renderHook(() => useExplainAvailable(), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe('useExplainRegime', () => {
  const ANSWER = { text: 'A storm.', citations: [], checked: true, note: null, cached: false };

  it('asks the fixed question, or a card by its key', async () => {
    POST.mockResolvedValue({ data: ANSWER, response: new Response(null, { status: 200 }) });
    const { result } = renderHook(() => useExplainRegime(), { wrapper });
    result.current.mutate({});
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(POST).toHaveBeenLastCalledWith('/regime/explain', {
      body: { question: 'what is happening?', card: null },
    });
    result.current.mutate({ card: 'sahm' });
    await waitFor(() => {
      expect(POST).toHaveBeenLastCalledWith('/regime/explain', { body: { card: 'sahm' } });
    });
  });
});
