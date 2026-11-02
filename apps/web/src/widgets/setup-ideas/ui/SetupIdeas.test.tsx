import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SetupIdea, SetupIdeas as Data } from '@/entities/idea';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { SetupIdeas } from './SetupIdeas';

const hooks = vi.hoisted(() => ({ useSetupIdeas: vi.fn() }));
vi.mock('@/entities/idea', () => ({ useSetupIdeas: hooks.useSetupIdeas }));
vi.mock('@/entities/edge', () => ({
  verdictLabel: (v: string) => (v === 'works' ? 'Works' : 'Promising'),
  verdictTone: () => 'positive',
}));
vi.mock('@/features/guide-help', () => ({ termHelp: () => null }));

const idea = (instrumentId: string, symbol: string, rank: number): SetupIdea => ({
  rank,
  instrumentId,
  symbol,
  name: `${symbol} Inc`,
  setupId: 'drift',
  place: rank,
  alsoIn: [],
  watchOut: ['liquidity_risk'],
  metrics: [{ name: 'hv30', value: 0.4 }],
  regime: null,
});
const a = idea('EQ:A', 'AAA', 1);
const listed: Data = {
  session: '2026-10-02',
  state: 'listed',
  total: 1,
  leftOut: [{ kind: 'no_verdict', count: 2 }],
  ideas: [a],
  groups: [
    {
      edgeId: 'drift',
      name: 'Post-earnings drift',
      level: 'works',
      liftPts: 3.2,
      oosTrades: 120,
      basisHorizon: 20,
      basisScreener: 'drift_scr',
      state: 'picked',
      unknown: null,
      picked: 1,
      shown: 1,
      ideas: [a],
    },
    {
      edgeId: 'quiet',
      name: 'Quiet setup',
      level: 'promising',
      liftPts: null,
      oosTrades: null,
      basisHorizon: null,
      basisScreener: 'quiet_scr',
      state: 'not_a_decision_day',
      unknown: null,
      picked: 0,
      shown: 0,
      ideas: [],
    },
  ],
};

const props = {
  tab: 'stocks' as const,
  unproven: <Text>pool here</Text>,
  onOpen: vi.fn(),
  onOpenEdge: vi.fn(),
  onOpenIdea: vi.fn(),
};

stubElementSize();

describe('SetupIdeas', () => {
  beforeEach(() => {
    hooks.useSetupIdeas.mockReset();
    props.onOpen.mockReset();
    props.onOpenIdea.mockReset();
  });

  it('groups the picks by setup with the labelled figures and the left-out counts', async () => {
    hooks.useSetupIdeas.mockReturnValue(fakeQuery<Data>(listed));
    const { container } = render(<SetupIdeas {...props} />);
    expect(screen.getByText('Post-earnings drift')).toBeVisible();
    expect(screen.getByText(/Backtested \(hypothetical\) · lift 3\.2 pts · 120/)).toBeVisible();
    expect(screen.getByText('Not a decision day')).toBeVisible();
    expect(screen.getByText('2 no readable verdict')).toBeVisible();
    expect(screen.queryByText('pool here')).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("opens a name in the detail and from there in Explore with the setup's screener", async () => {
    hooks.useSetupIdeas.mockReturnValue(fakeQuery<Data>(listed));
    render(<SetupIdeas {...props} />);
    await userEvent.click(screen.getByText('AAA'));
    await userEvent.click(await screen.findByRole('button', { name: 'Open AAA in Explore' }));
    expect(props.onOpen).toHaveBeenCalledWith('AAA', 'drift_scr');
    await userEvent.click(screen.getByRole('button', { name: 'Open the idea' }));
    expect(props.onOpenIdea).toHaveBeenCalledWith('AAA', 'drift');
  });

  it('shows the Unproven section, not the list, when no setup qualifies', () => {
    hooks.useSetupIdeas.mockReturnValue(
      fakeQuery<Data>({ ...listed, state: 'unproven', groups: [], ideas: [] }),
    );
    render(<SetupIdeas {...props} />);
    expect(screen.getByText('Unproven')).toBeVisible();
    expect(screen.getByText('pool here')).toBeVisible();
  });

  it('says so when nothing is stored', () => {
    hooks.useSetupIdeas.mockReturnValue(fakeQuery<Data>(null as unknown as Data));
    render(<SetupIdeas {...props} />);
    expect(screen.getByText('Nothing is stored for this session yet.')).toBeVisible();
  });
});
