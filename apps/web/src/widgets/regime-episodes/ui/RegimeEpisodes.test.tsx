import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Text } from '@algotrade/ui';

import { regimeFixture, type Regime, type RegimeEpisode } from '@/entities/regime';
import { RegimeRangeProvider, useRegimeRange } from '@/features/regime-range';
import { fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { RegimeEpisodes } from './RegimeEpisodes';

stubElementSize();

const hooks = vi.hoisted(() => ({ useRegime: vi.fn(), useRegimeEpisodes: vi.fn() }));
vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRegime: hooks.useRegime,
  useRegimeEpisodes: hooks.useRegimeEpisodes,
}));

const episode = (overrides: Partial<RegimeEpisode>): RegimeEpisode => ({
  key: 'covid_2020',
  name: 'Covid crash, early 2020',
  kind: 'shock',
  peak: '2020-02-19',
  trough: '2020-03-23',
  recovered: '2020-08-18',
  spxDrawdown: -0.34,
  nasdaqDrawdown: -0.3,
  recession: true,
  nberStart: '2020-02-01',
  nberEnd: '2020-04-01',
  cause: '',
  notes: '',
  knownFrom: '2020-03-23',
  ...overrides,
});
const EPISODES = [
  episode({
    key: 'gfc_2008',
    name: 'Financial crisis, 2007-09',
    kind: 'recession',
    peak: '2007-10-09',
    trough: '2009-03-09',
    recovered: '2013-03-28',
    spxDrawdown: -0.57,
  }),
  episode({}),
  episode({
    key: 'tariffs_2025',
    name: 'Tariff shock, spring 2025',
    peak: '2025-02-19',
    trough: '2025-04-08',
    recovered: null,
    spxDrawdown: -0.19,
    recession: false,
  }),
];

function Window() {
  const range = useRegimeRange('2026-10-02');
  return <Text>{`window ${range.window.start} to ${range.window.end}`}</Text>;
}

beforeEach(() => {
  hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
  hooks.useRegimeEpisodes.mockReturnValue(fakeQuery({ episodes: EPISODES, recessions: [] }));
});

describe('RegimeEpisodes', () => {
  it('lists each fall, newest first, with its dates, depth, recovery and recession', () => {
    render(<RegimeEpisodes />);
    const rows = screen.getAllByRole('row').slice(1);
    expect(rows[0]).toHaveTextContent('Tariff shock, spring 2025');
    expect(rows[0]).toHaveTextContent('Not yet');
    expect(rows[0]).toHaveTextContent(/[-−]19%/);
    expect(rows[1]).toHaveTextContent('Covid crash, early 2020');
    expect(rows[1]).toHaveTextContent('Shock or re-rating');
    expect(rows[2]).toHaveTextContent('Recession bear market');
    expect(rows[2]).toHaveTextContent(/[-−]57%/);
    expect(screen.getByRole('grid', { name: 'Market falls' })).toBeVisible();
  });

  it('sets every chart to a year before the peak through six months after the recovery', async () => {
    render(
      <RegimeRangeProvider>
        <RegimeEpisodes />
        <Window />
      </RegimeRangeProvider>,
    );
    expect(screen.getByText('window 1971-01-01 to 2026-10-02')).toBeVisible();
    await userEvent.setup().click(screen.getByText('Covid crash, early 2020'));
    expect(screen.getByText('window 2019-02-19 to 2021-02-18')).toBeVisible();
  });

  it('runs an episode that has not recovered to the session', async () => {
    render(
      <RegimeRangeProvider>
        <RegimeEpisodes />
        <Window />
      </RegimeRangeProvider>,
    );
    await userEvent.setup().click(screen.getByText('Tariff shock, spring 2025'));
    expect(screen.getByText('window 2024-02-19 to 2026-10-02')).toBeVisible();
  });

  it('is empty without a regime, loading before the answer and an error on failure', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    const { rerender } = render(<RegimeEpisodes />);
    expect(screen.getByText('No market falls are stored for this session.')).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<RegimeEpisodes />);
    expect(screen.getByText('Loading the market falls')).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture(), { isError: true }));
    rerender(<RegimeEpisodes />);
    expect(screen.getByText('The market falls failed to load.')).toBeVisible();
  });
});
