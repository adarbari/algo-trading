import { IconButton } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { RecentRun } from '@/entities/screen';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ScreenerRunLine } from './ScreenerRunLine';

const hooks = vi.hoisted(() => ({ start: vi.fn(), role: vi.fn<() => string>() }));

vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRunScreener: () => ({
    start: hooks.start,
    run: undefined,
    running: false,
    error: null,
  }),
}));
vi.mock('@/entities/viewer', () => ({ useViewer: () => ({ data: { role: hooks.role() } }) }));
// The help button reads the Guide; its own test covers that.
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => <IconButton icon="info" label={`Help: ${id}`} />,
}));

const ran = (over: Partial<RecentRun> = {}): RecentRun => ({
  session: '2026-10-22',
  state: 'COMPLETE',
  served: true,
  runId: 'run-9',
  configVersion: 3,
  picked: 12,
  newPicks: 2,
  dropped: 1,
  leftOutShare: 0.08,
  notRun: null,
  ...over,
});
const gap = (served: boolean): RecentRun =>
  ran({
    session: served ? '2026-10-22' : '2026-10-21',
    state: 'NOT_RUN',
    served,
    runId: null,
    configVersion: null,
    picked: null,
    newPicks: null,
    dropped: null,
    leftOutShare: null,
    notRun: {
      code: 'NOT_RUN',
      kind: 'NOT_RUN',
      guideTerm: 'not_run',
      kindText: 'not run for this session',
      cause: null,
    },
  });

describe('ScreenerRunLine', () => {
  beforeEach(() => {
    hooks.start.mockReset();
    hooks.role.mockReturnValue('trader');
  });

  it('says the last run: session, state, version, picks, changes and what it left out', async () => {
    const { container } = render(<ScreenerRunLine id="vrp" runs={[gap(false), ran()]} />);
    expect(screen.getByText('Run 2026-10-22')).toBeInTheDocument();
    expect(screen.getByText('Complete')).toBeInTheDocument();
    expect(
      screen.getByText('v3 · 12 picked · +2 new, −1 dropped · Missing data for 8% of names'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help: run_state' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Run now' })).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('draws the strip, one square per session, each named by its day and state', () => {
    render(<ScreenerRunLine id="vrp" runs={[gap(false), ran({ state: 'PARTIAL' })]} />);
    const strip = screen.getByRole('group', { name: 'Last 2 sessions' });
    expect(
      within(strip)
        .getAllByRole('button')
        .map((b) => b.getAttribute('aria-label')),
    ).toEqual(['Oct 21: Not run', 'Oct 22: Partial, 12 picked']);
    expect(screen.getByRole('button', { name: 'Help: session_strip' })).toBeInTheDocument();
  });

  it('offers Run now, and the reason, when the served session has no run', async () => {
    render(
      <ScreenerRunLine
        id="vrp"
        runs={[ran({ session: '2026-10-21', served: false }), gap(true)]}
      />,
    );
    expect(screen.getByText('not run for this session')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Run now' }));
    expect(hooks.start).toHaveBeenCalledOnce();
  });

  it('does not offer Run now for a gap in the history of a session that ran', () => {
    render(<ScreenerRunLine id="vrp" runs={[gap(false), ran()]} />);
    expect(screen.queryByRole('button', { name: 'Run now' })).toBeNull();
  });

  it('gives only an admin the way to the run', () => {
    const view = render(<ScreenerRunLine id="vrp" runs={[ran()]} />);
    expect(screen.queryByRole('link', { name: 'Open in Screener runs' })).toBeNull();
    view.unmount();
    hooks.role.mockReturnValue('admin');
    render(<ScreenerRunLine id="vrp" runs={[ran()]} />);
    expect(screen.getByRole('link', { name: 'Open in Screener runs' })).toHaveAttribute(
      'href',
      '/admin/screener-runs?run=run-9',
    );
  });

  it('shows the cause chain the server sent, and nothing when it sent none', () => {
    const cause = {
      links: [
        {
          level: 'TABLE' as const,
          subject: 'chains/options',
          status: 'MISSING',
          message: 'no rows',
          runId: null,
        },
      ],
    };
    const withCause = gap(true);
    render(
      <ScreenerRunLine
        id="vrp"
        runs={[{ ...withCause, notRun: withCause.notRun && { ...withCause.notRun, cause } }]}
      />,
    );
    expect(screen.getByText('chains/options')).toBeInTheDocument();
  });

  it('renders nothing for no sessions', () => {
    const { container } = render(<ScreenerRunLine id="vrp" runs={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
