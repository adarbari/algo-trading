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

import { QualityChecksPanel } from './QualityChecksPanel';

describe('QualityChecksPanel', () => {
  it('lists the checks, failures first', async () => {
    serve({
      '/admin/quality': {
        run_id: 'q',
        session: '2026-10-02',
        status: 'partial',
        finished_at: null,
        checks: [
          { name: 'bars_fresh', status: 'PASS', detail: 'latest bars session 2026-10-02' },
          { name: 'chains_coverage', status: 'FAIL', detail: '86.2% of 4203 underlyings' },
        ],
      },
    });
    const { container } = renderWith(<QualityChecksPanel />);
    const table = await screen.findByRole('grid', { name: 'Quality checks' });
    const rows = table.querySelectorAll('[role="row"]');
    expect(rows[1]).toHaveTextContent('chains_coverage');
    expect(screen.getByRole('heading', { name: 'Quality checks · Fri 2 Oct' })).toBeInTheDocument();
    await expectAccessible(container);
  });

  it('says when there are no checks yet', async () => {
    serve({});
    renderWith(<QualityChecksPanel />);
    expect(await screen.findByText('No quality checks yet')).toBeInTheDocument();
  });
});
