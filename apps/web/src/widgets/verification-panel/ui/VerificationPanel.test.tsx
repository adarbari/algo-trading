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

import { VerificationPanel } from './VerificationPanel';

const VERIFICATION = {
  session: '2026-10-02',
  runIds: ['verify_ibkr-2026-10-02-20261003T183522Z'],
  instruments: 6,
  counts: { PASS: 42, WARN: 0, FAIL: 2, NA: 12 },
  byCheck: [{ check: 'low', counts: { PASS: 2, WARN: 0, FAIL: 2, NA: 0 } }],
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
    serve({ verification: VERIFICATION });
    const { container } = renderWith(<VerificationPanel />);
    expect(
      await screen.findByRole('grid', { name: 'Failing verification checks' }),
    ).toHaveTextContent('SPY');
    expect(screen.getByText(/6 instruments · 4.5% of graded checks failed/)).toBeInTheDocument();
    await expectAccessible(container);
  });

  it("opens a failing check's ticker in Explore on a click on its row", async () => {
    serve({ verification: VERIFICATION });
    const onOpen = vi.fn();
    renderWith(<VerificationPanel onOpen={onOpen} />);
    const grid = await screen.findByRole('grid', { name: 'Failing verification checks' });
    expect(grid.querySelector('[data-clickable]')).not.toBeNull();
    await userEvent.click(await screen.findByText('SPY'));
    expect(onOpen).toHaveBeenCalledExactlyOnceWith('SPY');
  });

  it('says when nothing failed, and when there is no run', async () => {
    serve({ verification: { ...VERIFICATION, failing: [] } });
    renderWith(<VerificationPanel />);
    expect(await screen.findByText('No failing checks')).toBeInTheDocument();
  });

  it('explains a session the verification did not run for', async () => {
    const unknown = { code: 'NO_PARTITION', detail: 'verification/ibkr has no partition' };
    serve({ verification: { ...VERIFICATION, counts: {}, byCheck: [], failing: [], unknown } });
    renderWith(<VerificationPanel />);
    expect(await screen.findByText('No verification for this session')).toBeInTheDocument();
  });

  it('explains an empty store', async () => {
    serve({});
    renderWith(<VerificationPanel />);
    expect(await screen.findByText('No verification for this session')).toBeInTheDocument();
  });
});
