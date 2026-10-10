import { ToastProvider } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import axe from 'axe-core';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';

import { ChainCoveragePanel } from './ChainCoveragePanel';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));
vi.mock('@/features/guide-help', () => ({ termHelp: (id: string) => `[help ${id}]` }));

const COVERAGE = {
  session: '2026-10-09',
  total: 4200,
  ok: 3380,
  share: 0.8048,
  statuses: [
    { code: 'OK', count: 3380 },
    { code: 'STALE_DATA', count: 758 },
  ],
  tiers: [
    { tier: 'core', total: 600, ok: 590, stale: 10 },
    { tier: 'rest', total: 3600, ok: 2790, stale: 748 },
  ],
  chronic: 622,
  chronicNames: ['AAA', 'BBB'],
  medianShare: 0.9,
  previousChronic: 500,
  drift: ['chain coverage 80.5% is 9.5 points below its median of the sessions before (90.0%)'],
};

function renderPanel() {
  return render(
    <ToastProvider>
      <TestQueryProvider>
        <ChainCoveragePanel />
      </TestQueryProvider>
    </ToastProvider>,
  );
}

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get: () => 400,
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get: () => 1000,
  });
});
afterAll(() => {
  Reflect.deleteProperty(HTMLElement.prototype, 'offsetHeight');
  Reflect.deleteProperty(HTMLElement.prototype, 'offsetWidth');
});

describe('ChainCoveragePanel', () => {
  it('shows the coverage, the tiers, the chronic names and the drift warning', async () => {
    vi.mocked(gql).mockResolvedValue({ chainCoverage: COVERAGE });
    const { container } = renderPanel();
    expect(await screen.findByText('80.5%')).toBeInTheDocument();
    expect(container).toHaveTextContent('3,380 of 4,200 optionable');
    expect(container).toHaveTextContent('622');
    expect(container).toHaveTextContent('2,790 of 3,600 OK');
    expect(container).toHaveTextContent('STALE_DATA 758');
    expect(container).toHaveTextContent('AAA, BBB');
    expect(container).toHaveTextContent('9.5 points below its median');
    expect(container).toHaveTextContent('[help chain_coverage]');
    const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(result.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  it('says so when the session has no chains run', async () => {
    vi.mocked(gql).mockResolvedValue({ chainCoverage: null });
    renderPanel();
    expect(await screen.findByText('No chains run for this session')).toBeInTheDocument();
  });

  it('shows an error with retry', async () => {
    vi.mocked(gql).mockRejectedValue(new Error('boom'));
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Chain coverage could not load.');
    });
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
