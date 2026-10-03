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
import userEvent from '@testing-library/user-event';
import { describe, it } from 'vitest';

import { ReviewItemsPanel } from './ReviewItemsPanel';

describe('ReviewItemsPanel', () => {
  it('counts each list and shows its items on demand', async () => {
    serve({
      '/admin/review/figi': {
        session: '2026-10-02',
        source: 'universe_build',
        items: [{ symbol: 'MMED', note: 'FIGI shared with MMEDV' }],
      },
      '/admin/review/leveraged': { session: '2026-10-02', source: 'reference', items: [] },
    });
    const { container } = renderWith(<ReviewItemsPanel />);
    const figi = await screen.findByRole('button', { name: /FIGI reviews/ });
    expect(figi).toHaveTextContent('1');
    await userEvent.click(figi);
    expect(await screen.findByText('FIGI shared with MMEDV')).toBeInTheDocument();
    await expectAccessible(container);
  });

  it('shows a list that failed to load', async () => {
    serve({
      '/admin/review/figi': null,
      '/admin/review/leveraged': { session: null, source: 'x', items: [] },
    });
    renderWith(<ReviewItemsPanel />);
    expect(await screen.findByRole('alert')).toHaveTextContent('FIGI reviews could not load.');
  });
});
