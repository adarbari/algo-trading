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

import { RecentRunsPanel } from './RecentRunsPanel';

const step = (name: string, status: string, durationS: number) => ({
  name,
  status,
  durationS,
  counts: {},
  reason: null,
  error: null,
  origin: null,
  originDurationS: null,
  startedAt: '2026-10-03T11:02:00Z',
  needs: [] as string[] | null,
  rerunsAfter: [],
});
const run = (runId: string, startedAt: string, durationS: number, chains: number) => ({
  runId,
  session: '2026-10-02',
  status: 'partial',
  startedAt,
  durationS,
  steps: [step('chains', 'PARTIAL', chains), step('earnings', 'COMPLETE', 84)],
  problems: ['steps not complete: chains'],
});

describe('RecentRunsPanel', () => {
  it('lists runs, newest open, and opens one at a time', async () => {
    serve({
      nightlyRuns: [
        run('n2', '2026-10-03T13:26:00Z', 1560, 1237),
        run('n1', '2026-10-03T11:01:00Z', 332, 18.5),
      ],
    });
    const { container } = renderWith(<RecentRunsPanel />);
    expect(await screen.findByRole('list', { name: 'Recent nightly runs' })).toHaveTextContent(
      '26m 0s',
    );
    expect(screen.getByRole('list', { name: /started 2026-10-03 13:26 UTC/ })).toHaveTextContent(
      '20m 37s',
    );
    expect(screen.getByText('steps not complete: chains')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Re-run nightly' })).toBeDisabled();
    await expectAccessible(container);
    await userEvent.click(screen.getByRole('button', { name: /2026-10-03 11:01 UTC/ }));
    expect(
      await screen.findByRole('list', { name: /started 2026-10-03 11:01 UTC/ }),
    ).toHaveTextContent('19s');
    expect(screen.queryByRole('list', { name: /started 2026-10-03 13:26 UTC/ })).toBeNull();
  });

  it('marks the steps a resumed attempt reused, with when and how long they took', async () => {
    const reusedStep = {
      ...step('macro', 'SUCCEEDED', 0),
      origin: 'nightly-first',
      originDurationS: 125,
      startedAt: '2026-10-03T03:46:12Z',
    };
    serve({
      nightlyRuns: [
        {
          ...run('n2', '2026-10-03T13:26:00Z', 60, 30),
          steps: [step('rollups', 'SUCCEEDED', 60), reusedStep],
        },
      ],
    });
    renderWith(<RecentRunsPanel />);
    expect(await screen.findByText('reused · 03:46 UTC · 2m 5s')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Step bar colours' })).toHaveTextContent(
      'Reused from earlier1',
    );
  });

  it('tells a step waiting on its source from one held by it, and marks what it needs', async () => {
    const held = (name: string, needs: string[]) => ({
      ...step(name, 'NOT_RUN', 0),
      reason: `needs ${needs.join(', ')} (WAITING)`,
      startedAt: null,
      needs,
    });
    serve({
      nightlyRuns: [
        {
          ...run('n2', '2026-10-03T13:26:00Z', 60, 30),
          steps: [
            { ...step('bars', 'WAITING', 90), reason: 'not published yet' },
            held('rollups', ['bars']),
            held('screens', ['rollups']),
            step('macro', 'SUCCEEDED', 5),
          ],
        },
      ],
    });
    renderWith(<RecentRunsPanel />);
    expect(await screen.findByText('waiting · 1m 30s · 11:02 UTC')).toBeInTheDocument();
    expect(screen.getAllByText('not run')).toHaveLength(2);
    await userEvent.click(screen.getByRole('button', { name: /rollups/ }));
    expect(screen.getByText('Needs: bars · Holds back: screens')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /bars/ })).not.toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: /rollups/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('says a run from before dependencies were recorded has none to show', async () => {
    serve({
      nightlyRuns: [
        {
          ...run('n2', '2026-10-03T13:26:00Z', 60, 30),
          steps: [{ ...step('bars', 'SUCCEEDED', 5), needs: null }],
        },
      ],
    });
    renderWith(<RecentRunsPanel />);
    await userEvent.click(await screen.findByRole('button', { name: /bars/ }));
    expect(screen.getByText('This run did not record its dependencies.')).toBeInTheDocument();
  });

  it('says when there are no runs', async () => {
    serve({ nightlyRuns: [] });
    renderWith(<RecentRunsPanel />);
    expect(await screen.findByText('No nightly runs yet')).toBeInTheDocument();
  });
});
