import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { call, callAt, callId, failureAt, usageFixture } from '@/entities/llm-usage';
import { gql, TestQueryProvider } from '@/shared/api';

import { UsageCallDetail } from './UsageCallDetail';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const view = (selected: string | null) => {
  vi.mocked(gql).mockResolvedValue({ llmUsage: usageFixture() });
  return render(
    <TestQueryProvider>
      <UsageCallDetail selected={selected} />
    </TestQueryProvider>,
  );
};

describe('UsageCallDetail', () => {
  it('shows every column of the chosen call', async () => {
    view(callId(callAt(0)));
    expect(await screen.findByText('claude-haiku-4-5')).toBeInTheDocument();
    expect(document.body).toHaveTextContent('1,200');
    expect(document.body).toHaveTextContent('$0.0027');
    expect(document.body).toHaveTextContent('llm_usage-2026-10-08-1');
    expect(screen.queryByText(/Not known/)).not.toBeInTheDocument();
  });

  it('names the values the log holds as null and why, never as zero', async () => {
    view(callId(callAt(2)));
    expect(
      await screen.findByText('Not known: Input tokens, Output tokens, Cost'),
    ).toBeInTheDocument();
    expect(screen.getByText('not available for this instrument')).toBeInTheDocument();
  });

  it('shows a rejected answer with its reason, the prompt and the raw answer', async () => {
    view(callId(failureAt(0)));
    expect(await screen.findByText('Answer rejected')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Error message' })).toHaveTextContent(
      "the model's answer is not JSON",
    );
    expect(screen.getByRole('region', { name: /Prompt sent/ })).toHaveTextContent(
      'stocks near support with rising volume',
    );
    expect(screen.getByRole('region', { name: 'Raw model answer' })).toHaveTextContent(
      'Sure! Support lines are not in the catalogue',
    );
    expect(document.body).toHaveTextContent('5,200 characters');
  });

  it('shows a failed provider attempt with its message and no raw answer', async () => {
    view(callId(failureAt(1)));
    expect(await screen.findByText('Provider failed')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Error message' })).toHaveTextContent(
      'claude_cli: the call timed out after 60 s',
    );
    expect(screen.queryByRole('region', { name: 'Raw model answer' })).not.toBeInTheDocument();
  });

  it('shows the cache tokens, the whole input and the call tags beside the regular input', async () => {
    const metered = call({
      inputTokens: 2,
      cacheReadTokens: 98000,
      cacheWriteTokens: 12000,
      totalInputTokens: 110002,
      callId: 'abc123',
      promptVersion: '1',
      callStage: 'repair',
    });
    const base = usageFixture();
    vi.mocked(gql).mockResolvedValue({ llmUsage: { ...base, recent: [metered, ...base.recent] } });
    render(
      <TestQueryProvider>
        <UsageCallDetail selected={callId(metered)} />
      </TestQueryProvider>,
    );
    await screen.findByText('Cache read tokens');
    expect(document.body).toHaveTextContent('98,000');
    expect(document.body).toHaveTextContent('12,000');
    expect(document.body).toHaveTextContent('110,002'); // 2 + 98,000 + 12,000
    expect(document.body).toHaveTextContent('abc123');
    expect(document.body).toHaveTextContent('repair');
  });

  it('shows a whole input the server says is not known as unknown, not as the small regular count', async () => {
    const old = call({ inputTokens: 2, totalInputTokens: null, costBasis: 'reported' });
    const base = usageFixture();
    vi.mocked(gql).mockResolvedValue({ llmUsage: { ...base, recent: [old, ...base.recent] } });
    render(
      <TestQueryProvider>
        <UsageCallDetail selected={callId(old)} />
      </TestQueryProvider>,
    );
    const label = await screen.findByText('Input tokens (incl. cache)');
    expect(label.parentElement?.parentElement).toHaveTextContent('Input tokens (incl. cache)—');
  });

  it('shows a cache count the log holds as null as unknown, not as zero', async () => {
    view(callId(callAt(0)));
    await screen.findByText('Cache read tokens');
    expect(screen.getByText('Cache read tokens').parentElement).not.toHaveTextContent(/\b0\b/);
  });

  it('shows no failure section for a call that succeeded', async () => {
    view(callId(callAt(0)));
    await screen.findByText('claude-haiku-4-5');
    expect(screen.queryByRole('region', { name: 'Error message' })).not.toBeInTheDocument();
  });

  it('asks for a call when none is chosen, and says one that left the list', async () => {
    view(null);
    expect(await screen.findByText('No call selected')).toBeInTheDocument();
  });

  it('says a chosen call is no longer in the latest list', async () => {
    view('gone~x~y');
    expect(
      await screen.findByText('That call is no longer in the latest list'),
    ).toBeInTheDocument();
  });
});
