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
import { describe, it } from 'vitest';

import { QualityChecksPanel } from './QualityChecksPanel';

describe('QualityChecksPanel', () => {
  it('lists the checks, failures first', async () => {
    serve({
      quality: {
        runId: 'q',
        session: '2026-10-02',
        status: 'partial',
        finishedAt: null,
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

  it('says when the session has no checks, with the reason', async () => {
    serve({
      quality: {
        session: '2026-10-02',
        runId: null,
        status: null,
        finishedAt: null,
        checks: [],
        unknown: { code: 'NOT_RUN', kind: 'NOT_RUN', guideTerm: 'not_run', cause: null },
      },
    });
    renderWith(<QualityChecksPanel />);
    expect(await screen.findByText('No quality checks for this session')).toBeInTheDocument();
    expect(screen.getByText(/Quality checks are not run for this session/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Quality checks · Fri 2 Oct' })).toBeInTheDocument();
  });

  it('says when nothing is stored yet', async () => {
    serve({});
    renderWith(<QualityChecksPanel />);
    expect(await screen.findByText('No quality checks for this session')).toBeInTheDocument();
  });
});
