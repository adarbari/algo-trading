import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  regimeFixture,
  type EpisodeSignals,
  type Regime,
  type RegimeEpisode,
  type SignalTiming,
} from '@/entities/regime';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { RegimeTiming } from './RegimeTiming';

// The help button and its drawer: GuideHelp.test.tsx.
vi.mock('@/features/guide-help', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    GuideHelp: ({ entry }: { entry: { kind: string; id: string } }) => (
      <Button>{`Help: ${entry.kind} ${entry.id}`}</Button>
    ),
  };
});

const hooks = vi.hoisted(() => ({
  useRegime: vi.fn(),
  useRegimeEpisodes: vi.fn(),
  useRegimeSignals: vi.fn(),
}));
vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRegime: hooks.useRegime,
  useRegimeEpisodes: hooks.useRegimeEpisodes,
  useRegimeSignals: hooks.useRegimeSignals,
}));

const episode = (key: string, name: string): RegimeEpisode => ({
  key,
  name,
  kind: 'recession',
  peak: '2007-10-09',
  trough: '2009-03-09',
  recovered: null,
  spxDrawdown: -0.57,
  nasdaqDrawdown: -0.5,
  recession: true,
  nberStart: null,
  nberEnd: null,
  cause: '',
  notes: '',
  knownFrom: '2009-03-09',
});
const timing = (overrides: Partial<SignalTiming>): SignalTiming => ({
  indicator: 'curve_10y3m',
  kind: 'SLOW',
  state: 'LED',
  flaggedDay: -40,
  clearedDay: 25,
  flaggedDayFromTrough: null,
  firstKnownDay: null,
  neverFired: false,
  unknownReason: null,
  ...overrides,
});
const SIGNALS: EpisodeSignals = {
  gate: timing({ indicator: 'gate', kind: 'GATE', flaggedDay: 8 }),
  indicators: [
    timing({}),
    timing({ indicator: 'sahm', state: 'NEVER_FIRED', flaggedDay: null, neverFired: true }),
  ],
};

function givenData(signals: ReadonlyMap<string, EpisodeSignals | null>) {
  hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
  hooks.useRegimeEpisodes.mockReturnValue(
    fakeQuery({
      episodes: [episode('gfc_2008', 'Financial crisis, 2007-09'), episode('covid', 'Covid crash')],
      recessions: [],
    }),
  );
  hooks.useRegimeSignals.mockReturnValue(fakeQuery(signals));
}

beforeEach(() => {
  hooks.useRegime.mockReset();
  hooks.useRegimeEpisodes.mockReset();
  hooks.useRegimeSignals.mockReset();
});

describe('RegimeTiming', () => {
  it('shows an overview row per fall, the key and the Guide help', () => {
    givenData(new Map([['gfc_2008', SIGNALS]]));
    render(<RegimeTiming />);
    const overview = screen.getByRole('list', {
      name: 'When each warning sign first flagged, by market fall',
    });
    expect(within(overview).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByRole('list', { name: 'Signal kinds' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Help: start reading_recession_signals' }),
    ).toBeVisible();
  });

  it('opens a fall to a row per signal with the server state in words', async () => {
    givenData(new Map([['gfc_2008', SIGNALS]]));
    const { container } = render(<RegimeTiming />);
    expect(
      screen.queryByRole('list', { name: 'Signals around Financial crisis, 2007-09' }),
    ).toBeNull();
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: /Financial crisis, 2007-09/ }));
    const detail = screen.getByRole('list', { name: 'Signals around Financial crisis, 2007-09' });
    expect(within(detail).getAllByRole('listitem')).toHaveLength(3);
    expect(within(detail).getByText('Never fired')).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('says so for a fall with no stored timing', async () => {
    givenData(new Map([['covid', null]]));
    render(<RegimeTiming />);
    await userEvent.setup().click(screen.getByRole('button', { name: /Covid crash/ }));
    expect(screen.getByText('No signal timing is stored for this fall.')).toBeVisible();
  });

  it('shows the error state with a retry', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    hooks.useRegimeEpisodes.mockReturnValue(fakeQuery({ episodes: [], recessions: [] }));
    hooks.useRegimeSignals.mockReturnValue(fakeQuery(undefined, { isError: true }));
    render(<RegimeTiming />);
    expect(screen.getByText('The signal timing failed to load.')).toBeVisible();
    expect(screen.getByRole('button', { name: /retry/i })).toBeVisible();
  });

  it('shows the empty state when no falls are stored', () => {
    givenData(new Map());
    hooks.useRegimeEpisodes.mockReturnValue(fakeQuery({ episodes: [], recessions: [] }));
    render(<RegimeTiming />);
    expect(screen.getByText('No market falls are stored for this session.')).toBeVisible();
  });
});
