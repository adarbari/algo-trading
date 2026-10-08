import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { callAt, callId, usageFixture } from '@/entities/llm-usage';
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
