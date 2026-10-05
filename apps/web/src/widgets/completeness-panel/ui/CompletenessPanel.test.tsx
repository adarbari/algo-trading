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

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it } from 'vitest';

import { CompletenessPanel } from './CompletenessPanel';

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
  runIds: ['option_chains-2026-10-02-20261003T093502Z'],
});

const COMPLETENESS = {
  sessions: ['2026-10-01', '2026-10-02'],
  datasets: ['bars/1d', 'chains/option_quotes'],
  lastClosed: '2026-10-02',
  cells: [
    cell('bars/1d', '2026-10-01', 'COMPLETE', 12594, 12590),
    cell('bars/1d', '2026-10-02', 'COMPLETE', 12601, 12594),
    cell('chains/option_quotes', '2026-10-01', 'MISSING', 0, null),
    cell('chains/option_quotes', '2026-10-02', 'PARTIAL', 3623, 4203),
  ],
};

describe('CompletenessPanel', () => {
  it('shows the grid, outlines the worst latest cell and reports a selection', async () => {
    serve({ completeness: COMPLETENESS });
    const onSelect = vi.fn();
    const { container } = renderWith(<CompletenessPanel onSelect={onSelect} />);
    const grid = await screen.findByRole('grid', { name: 'Completeness by dataset and session' });
    expect(grid).toHaveTextContent('Option chains');
    expect(grid).toHaveTextContent('86.2');
    await userEvent.click(screen.getAllByRole('gridcell', { selected: false })[0] as HTMLElement);
    expect(onSelect).toHaveBeenCalledWith({ dataset: 'bars/1d', session: '2026-10-01' });
    await expectAccessible(container);
  });

  it('shows loading, then an error with retry', async () => {
    serve({ completeness: FAIL });
    renderWith(<CompletenessPanel onSelect={vi.fn()} />);
    expect(screen.getByText('Loading completeness…')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Completeness could not load.');
    });
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
