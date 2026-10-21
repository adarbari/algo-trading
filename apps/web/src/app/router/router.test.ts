/** The router downloads the URL's page chunk at start-up, beside the viewer's round trip. */
import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

const loaded = vi.hoisted(() => vi.fn());
const reads = vi.hoisted(() => vi.fn());
vi.mock('@/pages/trader-regime', () => {
  loaded();
  return { RegimePage: () => null, prefetchRegimeReads: reads };
});

describe('router', () => {
  it('preloads the page chunk of the opened URL before any guard or loader runs', async () => {
    window.history.replaceState({}, '', '/regime');
    await import('./router');
    await vi.waitFor(() => {
      expect(loaded).toHaveBeenCalled();
    });
  });

  it("starts the opened trader page's reads at start-up, without waiting for the viewer", async () => {
    window.history.replaceState({}, '', '/regime');
    const { startEarlyReads } = await import('./router');
    startEarlyReads(new QueryClient());
    await vi.waitFor(() => {
      expect(reads).toHaveBeenCalled();
    });
  });
});
