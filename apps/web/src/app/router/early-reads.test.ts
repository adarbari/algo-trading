/** A trader page's reads start at start-up, before the guard; an admin page's do not. */
import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

const reads = vi.hoisted(() => vi.fn());
vi.mock('@/pages/trader-regime', () => ({ RegimePage: () => null, prefetchRegimeReads: reads }));

describe('startEarlyReads', () => {
  it("runs the opened trader page's loader without waiting for the viewer", async () => {
    window.history.replaceState({}, '', '/regime');
    const { startEarlyReads } = await import('./early-reads');
    startEarlyReads(new QueryClient());
    await vi.waitFor(() => {
      expect(reads).toHaveBeenCalled();
    });
  });

  it('starts nothing for an admin page (its role is known only after the viewer)', async () => {
    reads.mockClear();
    vi.resetModules(); // a new router reads the new location
    window.history.replaceState({}, '', '/admin/ingestion');
    const { startEarlyReads } = await import('./early-reads');
    startEarlyReads(new QueryClient());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(reads).not.toHaveBeenCalled();
  });
});
