import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { WhyIdeaPanel } from './WhyIdeaPanel';

const hooks = vi.hoisted(() => ({ useScreenerHits: vi.fn() }));

vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerHits: hooks.useScreenerHits,
  CriteriaScorecard: (props: { screenerId: string }) => (
    <Text>{`scorecard of ${props.screenerId}`}</Text>
  ),
}));

const hit = (id: string, name: string, decision: string, score: number | null) => ({
  screener: { id, name },
  result: {
    rank: 2,
    decision,
    score,
    reasons: 'iv rank near',
    flags: ['thin'],
    change: 'new',
    criteria: [],
  },
});

beforeEach(() => {
  hooks.useScreenerHits.mockReturnValue(
    fakeQuery({
      session: '2026-10-02',
      hits: [hit('vrp', 'VRP scanner', 'WATCH', 72.4), hit('mine', 'Mine', 'QUALIFIED', null)],
    }),
  );
});

describe('WhyIdeaPanel', () => {
  it("shows what the surfacing screener's run stored and opens its results", async () => {
    const onOpenScreener = vi.fn();
    const { container } = render(
      <WhyIdeaPanel symbol="AAPL" screenerId="vrp" onOpenScreener={onOpenScreener} />,
    );
    const list = screen.getByLabelText('VRP scanner on AAPL');
    expect(list).toHaveTextContent('Watch');
    expect(list).toHaveTextContent('#2');
    expect(list).toHaveTextContent('72');
    expect(list).toHaveTextContent('iv rank near');
    expect(list).toHaveTextContent('thin');
    expect(list).not.toHaveTextContent('Mine');
    expect(screen.getByText('scorecard of vrp')).toBeInTheDocument();
    screen.getByRole('button', { name: 'Open VRP scanner' }).click();
    expect(onOpenScreener).toHaveBeenCalledWith('vrp');
    await expectNoA11yViolations(container);
  });

  it('says so when that screener did not pick the ticker in the latest session', () => {
    render(<WhyIdeaPanel symbol="KO" screenerId="gone" onOpenScreener={() => undefined} />);
    expect(screen.getByText('gone did not pick KO in the latest session.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open gone' })).toBeInTheDocument();
  });
});
