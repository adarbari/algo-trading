import { ToastProvider } from '@algotrade/ui';
import { render } from '@testing-library/react';
import axe from 'axe-core';
import type { ReactNode } from 'react';
import { afterAll, beforeAll, expect, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  api: { GET: vi.fn() },
}));

/** Answers `api.GET(path)` from `routes` (a missing path is a 404, `null` an error 500). */
function serve(routes: Record<string, unknown>) {
  vi.mocked(api.GET).mockImplementation(((path: string) => {
    const data = routes[path];
    const status = data === undefined ? 404 : data === null ? 500 : 200;
    return Promise.resolve(
      status === 200
        ? { data, response: new Response(null, { status }) }
        : { error: { detail: `failed ${path}` }, response: new Response(null, { status }) },
    );
  }) as never);
}

function renderWith(ui: ReactNode) {
  return render(
    <ToastProvider>
      <TestQueryProvider>{ui}</TestQueryProvider>
    </ToastProvider>,
  );
}

// jsdom has no layout: give elements a size so tables have a viewport to fill.
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

async function expectAccessible(container: Element) {
  const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
  expect(result.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
}

import { screen } from '@testing-library/react';
import { describe, it } from 'vitest';

import { IngestionSummary } from './IngestionSummary';

const cell = (
  dataset: string,
  session: string,
  status: string,
  present: number,
  expected: number | null,
) => ({
  dataset,
  session,
  status,
  present,
  expected,
  basis: expected === null ? 'snapshot built' : 'optionable universe, fetch OK',
  run_ids: ['option_chains-2026-10-02-20261003T093502Z'],
});

const COMPLETENESS = {
  sessions: ['2026-10-01', '2026-10-02'],
  datasets: ['bars/1d', 'chains/option_quotes'],
  last_closed: '2026-10-02',
  cells: [
    cell('bars/1d', '2026-10-01', 'COMPLETE', 12594, 12590),
    cell('bars/1d', '2026-10-02', 'COMPLETE', 12601, 12594),
    cell('chains/option_quotes', '2026-10-01', 'MISSING', 0, null),
    cell('chains/option_quotes', '2026-10-02', 'PARTIAL', 3623, 4203),
  ],
};

const QUALITY = {
  run_id: 'data_quality-2026-10-02',
  session: '2026-10-02',
  status: 'partial',
  finished_at: null,
  checks: [
    { name: 'bars_fresh', status: 'PASS', detail: 'latest bars session 2026-10-02' },
    {
      name: 'chains_coverage',
      status: 'FAIL',
      detail: '86.2% of 4203 underlyings returned a chain',
    },
  ],
};
const RUN = {
  run_id: 'nightly-1',
  session: '2026-10-02',
  status: 'partial',
  started_at: '2026-10-03T13:26:00Z',
  finished_at: '2026-10-03T13:52:00Z',
  duration_s: 1560,
  steps: [
    { name: 'chains', status: 'PARTIAL', duration_s: 1237, reason: null, error: null, counts: {} },
  ],
  problems: [],
};

describe('IngestionSummary', () => {
  it('summarises completeness, quality, the run and open issues', async () => {
    serve({
      '/admin/ingestion/completeness': COMPLETENESS,
      '/admin/quality': QUALITY,
      '/admin/runs/nightly': [RUN],
      '/admin/review/figi': { session: '2026-10-02', source: 'x', items: [{ symbol: 'MMED' }] },
      '/admin/review/leveraged': { session: '2026-10-02', source: 'x', items: [] },
    });
    const { container } = renderWith(<IngestionSummary />);
    expect(await screen.findByText('1 pass · 1 fail')).toBeInTheDocument();
    expect(screen.getByText('26m 0s')).toBeInTheDocument();
    expect(screen.getByText(/chains_coverage: 86.2%/)).toBeInTheDocument();
    expect(screen.getByText(/1 FIGI reviews/)).toBeInTheDocument();
    expect(screen.queryByText(/Latest session not ingested/)).not.toBeInTheDocument();
    await expectAccessible(container);
  });

  it('warns when the exchange closed a session the store lacks', async () => {
    serve({
      '/admin/ingestion/completeness': { ...COMPLETENESS, last_closed: '2026-10-05' },
      '/admin/runs/nightly': [],
    });
    renderWith(<IngestionSummary />);
    expect(await screen.findByText(/Latest session not ingested/)).toBeInTheDocument();
  });
});
