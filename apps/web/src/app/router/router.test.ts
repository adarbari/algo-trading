/** The router downloads the URL's page chunk at start-up, beside the viewer's round trip. */
import { describe, expect, it, vi } from 'vitest';

const loaded = vi.hoisted(() => vi.fn());
vi.mock('@/pages/trader-regime', () => {
  loaded();
  return { RegimePage: () => null, prefetchRegimeReads: () => undefined };
});

describe('router', () => {
  it('preloads the page chunk of the opened URL before any guard or loader runs', async () => {
    window.history.replaceState({}, '', '/regime');
    await import('./router');
    await vi.waitFor(() => {
      expect(loaded).toHaveBeenCalled();
    });
  });
});
