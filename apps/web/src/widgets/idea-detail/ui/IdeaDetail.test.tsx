import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { IdeaDetail as Idea } from '@/entities/idea';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { IdeaDetail } from './IdeaDetail';

const hooks = vi.hoisted(() => ({ useIdeaDetail: vi.fn() }));
vi.mock('@/entities/idea', () => ({ useIdeaDetail: hooks.useIdeaDetail }));
vi.mock('@/entities/edge', () => ({
  verdictLabel: () => 'Works',
  verdictTone: () => 'positive',
}));
vi.mock('@/entities/guide', () => ({ edgeGuidePath: (id: string) => `/guide/edges/${id}` }));
vi.mock('@/entities/screen', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    CriteriaScorecard: (props: { entries: { id: string }[] }) => (
      <Text>{`criteria ${String(props.entries.length)}`}</Text>
    ),
  };
});
vi.mock('@/features/guide-help', () => ({ termHelp: () => null }));

const setup = {
  edgeId: 'drift',
  edgeName: 'Post-earnings drift',
  tab: 'stocks',
  level: 'works',
  place: 1,
};
const idea: Idea = {
  session: '2026-10-02',
  instrumentId: 'EQ:AAPL',
  symbol: 'AAPL',
  name: 'Apple Inc.',
  tab: 'stocks',
  setup,
  setups: [setup, { ...setup, edgeId: 'quiet', edgeName: 'Quiet setup', level: 'promising' }],
  why: {
    thesis: 'Prices adjust slowly.',
    mechanism: 'm',
    basisScreener: 'drift_scr',
    decision: 'QUALIFIED',
    criteria: [{ id: 'c1', field: 'f', outcome: 'PASS', value: 1, distance: null }],
    unknown: null,
  },
  exitRule: {
    edgeId: 'drift',
    holdSessions: 5,
    winners: 80,
    inSampleOnly: false,
    stop: { kind: 'HISTORY', fraction: 0.062, atr: null, multiple: null, winners: 80, beyond: 0.2 },
    unknown: null,
  },
  evidence: {
    level: 'works',
    result: 'Held out: lift 3.2 points on 120 trades.',
    basis: 'screen, 5 trading days',
    basisHorizon: 5,
    liftPts: 3.2,
    lift: 0.1,
    trades: 300,
    oosTrades: 120,
  },
  risks: {
    persistence: 'Slow-moving holders.',
    holdEnds: '2026-10-09',
    watchOut: ['liquidity_risk'],
    events: [{ date: '2026-10-07', label: 'Own earnings', name: 'AAPL earnings' }],
    unknown: null,
  },
  learn: 'drift',
};

const props = {
  symbol: 'AAPL',
  setup: undefined,
  onSetupChange: vi.fn(),
  onOpenEdge: vi.fn(),
  onOpenTicker: vi.fn(),
  onBack: vi.fn(),
};

describe('IdeaDetail', () => {
  beforeEach(() => {
    hooks.useIdeaDetail.mockReset();
    Object.values(props).forEach(
      (f) => typeof f === 'function' && 'mockReset' in f && f.mockReset(),
    );
  });

  it('shows the five sections with every figure labelled backtested', async () => {
    hooks.useIdeaDetail.mockReturnValue(fakeQuery<Idea>(idea));
    const { container } = render(<IdeaDetail {...props} />);
    for (const title of [
      'Why it is here',
      'Historical exit rule',
      'Evidence',
      'What could go wrong',
      'Learn this setup',
    ]) {
      expect(screen.getByRole('heading', { name: title })).toBeVisible();
    }
    expect(screen.getAllByText('Backtested (hypothetical)').length).toBeGreaterThan(2);
    expect(screen.getByText('Stop, below the entry close')).toBeVisible();
    expect(screen.getByText('AAPL earnings · Wed 7 Oct')).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('copies the exit rule as text', async () => {
    const write = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: write },
      configurable: true,
    });
    hooks.useIdeaDetail.mockReturnValue(fakeQuery<Idea>(idea));
    render(<IdeaDetail {...props} />);
    await userEvent.click(screen.getByRole('button', { name: 'Copy exit rule as text' }));
    expect(write).toHaveBeenCalledWith(
      expect.stringContaining('stop 6.2% below the entry close; hold 5 sessions'),
    );
  });

  it('switches setup when several picked the name, and opens the setup', async () => {
    hooks.useIdeaDetail.mockReturnValue(fakeQuery<Idea>(idea));
    render(<IdeaDetail {...props} />);
    await userEvent.click(screen.getByRole('radio', { name: 'Quiet setup' }));
    expect(props.onSetupChange).toHaveBeenCalledWith('quiet');
    await userEvent.click(screen.getByRole('button', { name: 'Open the setup' }));
    expect(props.onOpenEdge).toHaveBeenCalledWith('drift');
  });

  it('says so, with a way back, when no setup picked the name', async () => {
    hooks.useIdeaDetail.mockReturnValue(fakeQuery<Idea>(null as unknown as Idea));
    render(<IdeaDetail {...props} />);
    await userEvent.click(screen.getByRole('button', { name: 'Back to Ideas' }));
    expect(props.onBack).toHaveBeenCalledWith('stocks');
  });
});
