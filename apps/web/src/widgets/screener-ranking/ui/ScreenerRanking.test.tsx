import { ToastProvider } from '@algotrade/ui';
import userEvent from '@testing-library/user-event';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { IdeasData } from '@/entities/idea';
import { TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { ScreenerRanking } from './ScreenerRanking';

const hooks = vi.hoisted(() => ({ useIdeas: vi.fn() }));
vi.mock('@/entities/idea', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useIdeas: hooks.useIdeas,
}));

vi.mock('@/entities/edge', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    ScreenerOdds: ({ screenerId }: { screenerId: string }) => <Text>{`odds ${screenerId}`}</Text>,
  };
});
vi.mock('@/features/guide-help', () => ({ GuideHelp: () => null }));

const data: IdeasData = {
  session: '2026-10-02',
  total: 2,
  ideas: [],
  pausedTotal: 0,
  paused: [],
  screeners: [
    {
      id: 'vrp-scanner',
      name: 'VRP scanner',
      owner: 'abhinav',
      version: 3,
      picked: 14,
      notRun: null,
      top: [
        { symbol: 'AAPL', score: 84 },
        { symbol: 'MSFT', score: 79 },
      ],
    },
    {
      id: 'near-low',
      name: 'near-low',
      owner: 'abhinav',
      version: null,
      picked: 0,
      notRun: null,
      top: [],
    },
    {
      id: 'idle',
      name: 'Idle',
      owner: 'abhinav',
      version: 1,
      picked: 0,
      notRun: {
        code: 'NOT_RUN',
        kind: 'NOT_RUN',
        guideTerm: 'not_run',
        kindText: 'not run for this session',
        reason: null,
        cause: null,
      },
      top: [],
    },
  ],
};

const onNew = vi.fn();
const onOpenScreener = vi.fn();

function setup() {
  return render(
    <ToastProvider>
      <TestQueryProvider>
        <ScreenerRanking onNewScreener={onNew} onOpenScreener={onOpenScreener} />
      </TestQueryProvider>
    </ToastProvider>,
  );
}

beforeEach(() => {
  hooks.useIdeas.mockReturnValue(fakeQuery(data));
});

describe('ScreenerRanking', () => {
  it('lists the screeners in priority order with their finds', async () => {
    const { container } = setup();
    expect(screen.getByRole('heading', { name: 'Your screeners' })).toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('VRP scanner');
    expect(items[0]).toHaveTextContent('AAPL 84 · MSFT 79');
    expect(items[0]).toHaveTextContent('14');
    expect(items[1]).toHaveTextContent('No picks');
    expect(items[2]).toHaveTextContent('Not run for this session');
    expect(items[2]).toHaveTextContent('not run');
    await expectNoA11yViolations(container);
  });

  it("shows each screener's odds line", () => {
    setup();
    expect(screen.getByText('odds vrp-scanner')).toBeInTheDocument();
    expect(screen.getByText('odds near-low')).toBeInTheDocument();
  });

  it("opens a screener's results from its name", async () => {
    setup();
    await userEvent.setup().click(screen.getByRole('button', { name: 'VRP scanner' }));
    expect(onOpenScreener).toHaveBeenCalledWith('vrp-scanner');
  });

  it('shows loading, empty and error states', async () => {
    hooks.useIdeas.mockReturnValue(fakeQuery(undefined));
    const { unmount, container } = setup();
    expect(screen.getByText('Loading screeners…')).toBeInTheDocument();
    await expectNoA11yViolations(container);
    unmount();

    hooks.useIdeas.mockReturnValue(fakeQuery({ ...data, screeners: [] }));
    const empty = setup();
    expect(screen.getByText(/You have no screeners yet/)).toBeInTheDocument();
    await expectNoA11yViolations(empty.container);
    empty.unmount();

    const query = fakeQuery<IdeasData>(undefined, { isError: true, error: new Error('x') });
    hooks.useIdeas.mockReturnValue(query);
    const failed = setup();
    expect(screen.getByText('The screeners failed to load.')).toBeInTheDocument();
    await expectNoA11yViolations(failed.container);
  });
});
