import { ToastProvider } from '@algotrade/ui';
import { render } from '@testing-library/react';
import axe from 'axe-core';
import type { ReactNode } from 'react';
import { afterAll, beforeAll, expect, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

/** A `serve` value: the operation fails (an HTTP or GraphQL error). */
const FAIL = Symbol('fail');

/**
 * Answers `gql(document)` with `fields[<the operation's Query field>]`: a missing field is
 * null (nothing stored, no such thing), `FAIL` an error.
 */
function serve(fields: Record<string, unknown>) {
  vi.mocked(gql).mockImplementation((document: unknown) => {
    const field = /\{\s*(\w+)/.exec(String(document))?.[1] ?? '';
    const data = fields[field];
    return data === FAIL
      ? Promise.reject(new Error(`${field} failed`))
      : Promise.resolve({ [field]: data ?? null });
  });
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
      figiReview: {
        session: '2026-10-02',
        source: 'universe_build',
        items: [{ symbol: 'MMED', note: 'FIGI shared with MMEDV' }],
      },
      leverageReview: { session: '2026-10-02', source: 'reference', items: [] },
    });
    const { container } = renderWith(<ReviewItemsPanel />);
    const figi = await screen.findByRole('button', { name: /FIGI reviews/ });
    expect(figi).toHaveTextContent('1');
    await userEvent.click(figi);
    expect(await screen.findByText('FIGI shared with MMEDV')).toBeInTheDocument();
    await expectAccessible(container);
  });

  it("opens a review item's ticker in Explore on a click on its row", async () => {
    serve({
      figiReview: {
        session: '2026-10-02',
        source: 'universe_build',
        items: [{ symbol: 'MMED', note: 'FIGI shared with MMEDV' }],
      },
      leverageReview: { session: '2026-10-02', source: 'reference', items: [] },
    });
    const onOpen = vi.fn();
    renderWith(<ReviewItemsPanel onOpen={onOpen} />);
    await userEvent.click(await screen.findByRole('button', { name: /FIGI reviews/ }));
    await userEvent.click(await screen.findByText('FIGI shared with MMEDV'));
    expect(onOpen).toHaveBeenCalledExactlyOnceWith('MMED');
  });

  it('shows a list that failed to load', async () => {
    serve({
      figiReview: FAIL,
      leverageReview: { session: null, source: 'x', items: [] },
    });
    renderWith(<ReviewItemsPanel />);
    expect(await screen.findByRole('alert')).toHaveTextContent('FIGI reviews could not load.');
  });
});
