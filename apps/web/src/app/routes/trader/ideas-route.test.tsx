/**
 * The Ideas panels against the app's real query client and the real hook (only HTTP is faked):
 * whatever the API answers, the panel ends in data, empty or error, never "Loading…" for good.
 * A first-run store answers 200 with no session (an older API answered 404).
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from '@algotrade/ui';

import { api } from '@/shared/api';
import { IdeasPage } from '@/pages/trader-ideas';
import { stubElementSize } from '@/shared/lib/testing';

import { createQueryClient } from '../../providers/query-client';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn() } };
});

const GET = vi.mocked(api.GET);
stubElementSize();

function setup() {
  const client = createQueryClient();
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <IdeasPage
          onCompare={vi.fn()}
          onOpen={vi.fn()}
          onNewScreener={vi.fn()}
          onScreeners={vi.fn()}
          onOpenScreener={vi.fn()}
        />
      </QueryClientProvider>
    </ToastProvider>,
  );
}

beforeEach(() => {
  GET.mockReset();
});

describe('the Ideas page with the real query client', () => {
  it('says no screener has run yet, with a link to Screeners, when nothing is stored', async () => {
    GET.mockResolvedValue({
      data: { session: null, priority: [], screeners: [], total: 0, items: [] },
      response: new Response(null, { status: 200 }),
    });
    setup();
    expect(await screen.findByText(/No screener has run yet, so there/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Go to Screeners' })).toBeInTheDocument();
    expect(screen.queryByText('Loading ideas…')).not.toBeInTheDocument();
    expect(screen.queryByText('Loading screeners…')).not.toBeInTheDocument();
  });

  it('settles on the error state at once for a 404, without waiting on a retry', async () => {
    GET.mockResolvedValue({
      error: { detail: 'results/rule_screen: nothing stored' },
      response: new Response(null, { status: 404 }),
    });
    setup();
    expect(
      await screen.findByText('The ideas failed to load.', {}, { timeout: 500 }),
    ).toBeVisible();
    expect(GET).toHaveBeenCalledTimes(1);
  });
});
