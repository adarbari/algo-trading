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
  reason: null,
  error: null,
  counts: {},
});
const run = (runId: string, startedAt: string, durationS: number, chains: number) => ({
  runId,
  session: '2026-10-02',
  status: 'partial',
  startedAt,
  finishedAt: null,
  durationS,
  steps: [step('chains', 'PARTIAL', chains), step('earnings', 'COMPLETE', 84)],
  problems: ['steps not complete: chains'],
});

describe('RecentRunsPanel', () => {
  it('lists runs and shows the timing of the chosen one', async () => {
    serve({
      nightlyRuns: [
        run('n2', '2026-10-03T13:26:00Z', 1560, 1237),
        run('n1', '2026-10-03T11:01:00Z', 332, 18.5),
      ],
    });
    const { container } = renderWith(<RecentRunsPanel />);
    expect(await screen.findByRole('grid', { name: 'Recent nightly runs' })).toHaveTextContent(
      '26m 0s',
    );
    expect(screen.getByRole('list', { name: /started 2026-10-03 13:26 UTC/ })).toHaveTextContent(
      '20m 37s',
    );
    expect(screen.getByRole('button', { name: 'Re-run nightly' })).toBeDisabled();
    await expectAccessible(container);
    await userEvent.click(screen.getByText('2026-10-03 11:01 UTC'));
    expect(
      await screen.findByRole('list', { name: /started 2026-10-03 11:01 UTC/ }),
    ).toHaveTextContent('19s');
  });

  it('says when there are no runs', async () => {
    serve({ nightlyRuns: [] });
    renderWith(<RecentRunsPanel />);
    expect(await screen.findByText('No nightly runs yet')).toBeInTheDocument();
  });
});
