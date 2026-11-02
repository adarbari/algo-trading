/**
 * The Ideas panels against the app's real query client and the real hook (only HTTP is faked):
 * whatever the API answers, the panel ends in data, empty or error, never "Loading…" for good.
 * A first-run store answers `ideas: null` (nothing stored); a request error settles at once.
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from '@algotrade/ui';

import { gql, GraphQLRequestError } from '@/shared/api';
import { IdeasPage } from '@/pages/trader-ideas';
import { stubElementSize } from '@/shared/lib/testing';

import { createQueryClient } from '../../providers/query-client';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);
stubElementSize();

function setup() {
  const client = createQueryClient();
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <IdeasPage
          search={{}}
          onSearchChange={vi.fn()}
          onCompare={vi.fn()}
          onOpen={vi.fn()}
          onScreeners={vi.fn()}
          onOpenScreener={vi.fn()}
          onOpenRegime={vi.fn()}
          onOpenEdge={vi.fn()}
        />
      </QueryClientProvider>
    </ToastProvider>,
  );
}

beforeEach(() => {
  GQL.mockReset();
});

describe('the Ideas page with the real query client', () => {
  it('says nothing is stored yet when the API has no ideas for the session', async () => {
    GQL.mockResolvedValue({ ideas: null, setupIdeas: null });
    setup();
    expect(await screen.findByText('Nothing is stored for this session yet.')).toBeInTheDocument();
    expect(screen.queryByText('Loading ideas…')).not.toBeInTheDocument();
  });

  it('settles on the error state at once for a request error, without waiting on a retry', async () => {
    GQL.mockRejectedValue(
      new GraphQLRequestError([{ message: 'no', extensions: { code: 'BAD_REQUEST' } }]),
    );
    setup();
    expect(
      await screen.findByText('The ideas failed to load.', {}, { timeout: 500 }),
    ).toBeVisible();
    // The regime strip reads too; the setup-ideas read itself is asked once (no retry).
    const asked = GQL.mock.calls.filter(([document]) =>
      String(document).includes('query SetupIdeas'),
    );
    expect(asked).toHaveLength(1);
  });
});
