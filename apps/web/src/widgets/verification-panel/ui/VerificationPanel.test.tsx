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

import { VerificationPanel } from './VerificationPanel';

const VERIFICATION = {
  session: '2026-10-02',
  run_ids: ['verify_ibkr-2026-10-02-20261003T183522Z'],
  instruments: 6,
  counts: { PASS: 42, WARN: 0, FAIL: 2, NA: 12 },
  by_check: [{ check: 'low', counts: { PASS: 2, WARN: 0, FAIL: 2, NA: 0 } }],
  failing: [
    {
      instrument_id: 'EQ:BBG000BDTBL9',
      symbol: 'SPY',
      check: 'low',
      status: 'FAIL',
      ours: 680.5868,
      theirs: 682.68,
      diff: 0.003066,
      tolerance: 0.001,
      note: 'rel diff; worst session 2025-12-22 of 260 compared',
    },
  ],
};

describe('VerificationPanel', () => {
  it('shows counts by status and the failing checks', async () => {
    serve({ '/admin/verification/ibkr': VERIFICATION });
    const { container } = renderWith(<VerificationPanel />);
    expect(
      await screen.findByRole('grid', { name: 'Failing verification checks' }),
    ).toHaveTextContent('SPY');
    expect(screen.getByText(/6 instruments · 4.5% of graded checks failed/)).toBeInTheDocument();
    await expectAccessible(container);
  });

  it('says when nothing failed, and when there is no run', async () => {
    serve({ '/admin/verification/ibkr': { ...VERIFICATION, failing: [] } });
    renderWith(<VerificationPanel />);
    expect(await screen.findByText('No failing checks')).toBeInTheDocument();
  });

  it('explains a missing verification run', async () => {
    serve({});
    renderWith(<VerificationPanel />);
    expect(await screen.findByText('No verification run yet')).toBeInTheDocument();
  });
});
