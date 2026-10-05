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

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it } from 'vitest';

import { DrilldownPanel } from './DrilldownPanel';

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
const RUN = {
  runId: 'option_chains-2026-10-02-20261003T093502Z',
  job: 'option_chains',
  session: '2026-10-02',
  status: 'partial',
  startedAt: '2026-10-03T09:35:02Z',
  finishedAt: '2026-10-03T13:51:00Z',
  durationS: 15358,
  itemsTotal: 4204,
  itemsByStatus: { OK: 3624, STALE_DATA: 515, NO_CHAIN: 63, NO_STANDARD_SERIES: 2 },
  failures: [],
  stats: { order_tiers: { priority: 536, liquidity: 1840, rest: 1827 } },
};
const DETAIL = {
  cell: cell('chains/option_quotes', '2026-10-02', 'PARTIAL', 3623, 4203),
  job: 'option_chains',
  groups: [
    {
      reason: 'STALE_DATA: chain is for <date>',
      count: 515,
      examples: ['AAMI', 'AAPD'],
      statuses: [],
    },
    { reason: 'NO_CHAIN', count: 63, examples: ['ALBG'], statuses: ['NO_CHAIN'] },
  ],
  runs: [RUN],
};

describe('DrilldownPanel', () => {
  it('drills into the default cell: statuses, tiers, grouped issues, actions', async () => {
    serve({
      completeness: COMPLETENESS,
      ingestionCell: DETAIL,
      run: RUN,
      runItems: [
        { key: 'EQ:ACIU', code: 'STALE_DATA', status: 'STALE_DATA: chain is for 2026-10-01' },
      ],
    });
    const { container } = renderWith(<DrilldownPanel />);
    expect(
      await screen.findByRole('heading', { name: 'Option chains · Fri 2 Oct' }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/3,623 of 4,203 expected/)).toBeInTheDocument();
    expect(
      screen.getByRole('list', { name: 'Underlyings by fetch priority tier' }),
    ).toHaveTextContent('1,840');
    expect(screen.getByRole('button', { name: /STALE_DATA: chain is for <date>/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByText('AAMI · AAPD · … 513 more')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Re-run option chains/ })).toBeDisabled();
    await expectAccessible(container);

    await userEvent.click(screen.getByRole('button', { name: 'Open run record' }));
    const drawer = await screen.findByRole('dialog', { name: 'Run record' });
    await waitFor(() => {
      expect(within(drawer).getByText('EQ:ACIU')).toBeInTheDocument();
    });
    expect(await within(drawer).findByText('4h 15m')).toBeInTheDocument();
  });

  it('shows the error of a failed drill-down', async () => {
    serve({ ingestionCell: FAIL });
    renderWith(<DrilldownPanel selected={{ dataset: 'bars/1d', session: '2026-10-02' }} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('The drill-down could not load.');
  });
});
