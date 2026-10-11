import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DECAY_FIXTURE, edgeFixture } from '@/entities/edge';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EdgeSureness } from './EdgeSureness';

const hooks = vi.hoisted(() => ({ useEdgeDecay: vi.fn() }));

vi.mock('@/entities/edge', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEdgeDecay: hooks.useEdgeDecay,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
    Labelled: ({ text, help }: { text: string; help: string }) => (
      <Text>{`${text} help ${help}`}</Text>
    ),
  };
});

stubElementSize();

const momentum = edgeFixture('momentum_12_1');
const waiting = edgeFixture('sp500_index_changes');

beforeEach(() => {
  hooks.useEdgeDecay.mockReturnValue(fakeQuery(DECAY_FIXTURE));
});

describe('EdgeSureness', () => {
  it('draws the in-sample deciles and places the lift among the random-pick backtests', async () => {
    const { container } = render(
      <EdgeSureness edgeId="momentum_12_1" verdict={momentum.verdict} />,
    );
    expect(screen.getByRole('heading', { level: 2, name: 'How sure' })).toBeInTheDocument();
    const bars = screen.getByRole('list', { name: 'Mean outcome by decile' });
    const rows = within(bars).getAllByRole('listitem');
    expect(rows).toHaveLength(10);
    expect(rows[0]).toHaveTextContent('Decile 1+9.0%');
    expect(rows[9]).toHaveTextContent('Decile 10−7.0%');
    expect(screen.getByRole('img', { name: /Lift of random-pick backtests/ })).toBeInTheDocument();
    expect(
      screen.getByText('Beats 96% of 1,000 random backtests after 3 variants tried.'),
    ).toBeInTheDocument();
    for (const id of ['edge_how_sure', 'top_vs_bottom_decile', 'robustness', 'decay']) {
      expect(screen.getAllByText(`help ${id}`).length).toBeGreaterThan(0);
    }
    await expectNoA11yViolations(container);
  });

  it('shows the variants, deflated Sharpe, haircut Sharpe and chance of overfitting with the sentence', () => {
    render(<EdgeSureness edgeId="momentum_12_1" verdict={momentum.verdict} />);
    for (const [label, value] of [
      ['Variants tried help variants_tried', '3'],
      ['Deflated Sharpe help deflated_sharpe', '0.90'],
      ['Haircut Sharpe help haircut_sharpe', '0.40'],
    ] as const) {
      expect(screen.getByText(label).closest('div')).toHaveTextContent(value);
    }
    expect(
      screen.getByText('Chance of overfitting help overfitting_probability'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Sharpe 1.10 over 70 trades with 3 variants becomes 0.40.'),
    ).toBeInTheDocument();
  });

  it('says what is missing instead of drawing zeros when a run stored no deciles or draws', () => {
    render(<EdgeSureness edgeId="sp500_index_changes" verdict={waiting.verdict} />);
    expect(screen.getByText('Not stored for this result.')).toBeInTheDocument();
    expect(screen.getByText('No random-pick backtests for this result.')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Mean outcome by decile' })).not.toBeInTheDocument();
  });

  it('draws the decay by stage and says why a stage has no bar', () => {
    render(<EdgeSureness edgeId="momentum_12_1" verdict={momentum.verdict} />);
    const bars = screen.getByRole('list', { name: 'Decay by stage' });
    const rows = within(bars).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('PublishedNot given');
    expect(rows[1]).toHaveTextContent('In-sample · n=64+6.0 pts');
    expect(rows[2]).toHaveTextContent('Out-of-sample · n=6+5.0 pts');
    expect(rows[3]).toHaveTextContent('Live · n=0Not measured live');
  });

  it('links the published figure to its source', () => {
    hooks.useEdgeDecay.mockReturnValue(
      fakeQuery({
        ...DECAY_FIXTURE,
        published: {
          measure: 'lift_pts',
          value: 4,
          horizonSessions: 20,
          sample: 30,
          source: { title: 'Jegadeesh and Titman 1993', url: 'https://example.org/jt1993' },
        },
        bars: [{ period: 'published', value: 4, n: null, state: 'measured' }],
      }),
    );
    render(<EdgeSureness edgeId="momentum_12_1" verdict={momentum.verdict} />);
    expect(screen.getByRole('link', { name: /Jegadeesh and Titman 1993/ })).toHaveAttribute(
      'href',
      'https://example.org/jt1993',
    );
  });

  it('shows the decay loading, failed with a retry, and empty without a basis', async () => {
    hooks.useEdgeDecay.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<EdgeSureness edgeId="momentum_12_1" verdict={momentum.verdict} />);
    expect(screen.getByText('Loading the decay…')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useEdgeDecay.mockReturnValue(failed);
    rerender(<EdgeSureness edgeId="momentum_12_1" verdict={momentum.verdict} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useEdgeDecay.mockReturnValue(fakeQuery(null));
    rerender(<EdgeSureness edgeId="momentum_12_1" verdict={momentum.verdict} />);
    expect(screen.getByText('No decay: the verdict has no basis yet.')).toBeInTheDocument();
  });
});
