import { ToastProvider } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import axe from 'axe-core';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';

import { KnownCoveragePanel } from './KnownCoveragePanel';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => `[help ${id}]`,
  helped: ({ help, ...column }: { help?: { id: string } }) =>
    help ? { ...column, headerAction: `[help ${help.id}]` } : column,
}));

const COVERAGE = {
  session: '2026-10-23',
  runId: 'night',
  byType: [
    { securityType: 'COMMON_STOCK', names: 5000, rows: 5000, known: 4800, share: 0.96 },
    { securityType: 'ETF', names: 4000, rows: 4000, known: 0, share: 0 },
  ],
  gaps: [
    { gap: 'BLANK_CHECK', names: 30 },
    { gap: 'NO_FACTS', names: 170 },
  ],
  unknown: null,
};

function renderPanel() {
  return render(
    <ToastProvider>
      <TestQueryProvider>
        <KnownCoveragePanel />
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

describe('KnownCoveragePanel', () => {
  it('shows rows stored beside known values, so stored ETF rows do not read as known', async () => {
    vi.mocked(gql).mockResolvedValue({ knownCoverage: COVERAGE });
    const { container } = renderPanel();
    const byType = await screen.findByRole('grid', {
      name: 'Fundamentals share count by security type',
    });
    expect(byType).toHaveTextContent('ETF');
    expect(byType).toHaveTextContent('4,000');
    expect(byType).toHaveTextContent('96.0%');
    expect(byType).toHaveTextContent('0.0%');
    const gaps = screen.getByRole('grid', { name: 'Operating companies without a share count' });
    expect(gaps).toHaveTextContent('Blank-check company');
    expect(gaps).toHaveTextContent('No share count filed');
    expect(container).toHaveTextContent('[help known_value_coverage]');
    const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(result.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  it('says when the session has no breakdown, with the reason', async () => {
    vi.mocked(gql).mockResolvedValue({
      knownCoverage: {
        session: '2026-10-23',
        runId: null,
        byType: [],
        gaps: [],
        unknown: {
          code: 'NOT_RUN',
          kind: 'NOT_RUN',
          guideTerm: 'not_run',
          kindText: 'not run for this session',
          cause: null,
        },
      },
    });
    renderPanel();
    expect(await screen.findByText('No known-value counts for this session')).toBeInTheDocument();
    expect(screen.getByText(/They are not run for this session/)).toBeInTheDocument();
  });

  it('shows an error with retry', async () => {
    vi.mocked(gql).mockRejectedValue(new Error('boom'));
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Known values could not load.');
    });
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
