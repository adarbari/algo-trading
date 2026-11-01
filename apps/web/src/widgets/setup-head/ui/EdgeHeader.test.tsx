import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { edgeFixture } from '@/entities/edge';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { EdgeHeader } from './EdgeHeader';

vi.mock('@/entities/edge', async (importOriginal) => {
  const { Text } = await import('@algotrade/ui');
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    EdgeLiveBadge: ({ edgeId }: { edgeId: string }) => <Text>{`live badge ${edgeId}`}</Text>,
  };
});
vi.mock('@/features/edge-evaluation', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RunEvaluation: ({ edgeId }: { edgeId: string }) => <Text>{`run ${edgeId}`}</Text> };
});
vi.mock('@/features/edge-follow', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    EdgeActions: ({ edge }: { edge: { id: string } }) => <Text>{`actions ${edge.id}`}</Text>,
  };
});
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
    GuideHelp: ({ entry }: { entry: { kind: string; id: string } }) => (
      <Text>{`guide ${entry.kind} ${entry.id}`}</Text>
    ),
  };
});

const momentum = edgeFixture('momentum_12_1');
const mine = edgeFixture('my_momentum');
const waiting = edgeFixture('sp500_index_changes');
const header = (edge = momentum, onBack = vi.fn()) =>
  render(<EdgeHeader edge={edge} onBack={onBack} onEdit={vi.fn()} />);

describe('EdgeHeader', () => {
  it('gives a site edge a button to its Guide entry, and a user’s own edge none', () => {
    header();
    expect(screen.getByText('guide edge momentum_12_1')).toBeInTheDocument();
    header(mine);
    expect(screen.queryByText('guide edge my_momentum')).toBeNull();
  });

  it('shows the name, verdict with the server headline, the actions and the live badge', async () => {
    const { container } = header();
    expect(screen.getByRole('heading', { level: 1, name: 'Momentum 12-1' })).toBeInTheDocument();
    expect(screen.getByText('live badge momentum_12_1')).toBeInTheDocument();
    expect(screen.getAllByText('Promising').length).toBeGreaterThan(0);
    expect(screen.getByText(/Out-of-sample, momentum_12_1, 20 trading days/)).toBeInTheDocument();
    expect(screen.getByText('run momentum_12_1')).toBeInTheDocument();
    expect(screen.getByText('actions momentum_12_1')).toBeInTheDocument();
    for (const id of ['verdict', 'edge_status', 'edge_state', 'edge_copy', 'run_backtest']) {
      expect(screen.getAllByText(`help ${id}`).length).toBeGreaterThan(0);
    }
    await expectNoA11yViolations(container);
  });

  it('says whose edge it is, the official result date, the data it read and the basis', () => {
    header();
    expect(screen.getByText('Site edge · Candidate')).toBeInTheDocument();
    expect(screen.getByText('Official result 5 Oct')).toBeInTheDocument();
    expect(screen.getByText('data to 2 Oct')).toBeInTheDocument();
    expect(screen.getByText('momentum_12_1, 20 trading days')).toBeInTheDocument();
    for (const id of ['official_result', 'verdict_basis']) {
      expect(screen.getAllByText(`help ${id}`).length).toBeGreaterThan(0);
    }
  });

  it('shows the evaluation line under the verdict, and none for an edge with no run', () => {
    header();
    expect(screen.getByText('Evaluated 2 Oct, run 1')).toBeInTheDocument();
    cleanup();
    header(waiting);
    expect(screen.queryByText(/^Evaluated /)).toBeNull();
  });

  it('says what would change the verdict: the sentence, the meters with the projected date and the checks', () => {
    header();
    expect(
      screen.getByRole('heading', { name: 'What would change the verdict' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Promising needs 40 out-of-sample trades: 6 so far, 34 to go.'),
    ).toBeInTheDocument();
    const oos = screen.getByRole('meter', { name: 'Out-of-sample trades' });
    expect(oos).toHaveAttribute('aria-valuenow', '6');
    expect(oos).toHaveAttribute('aria-valuemax', '60');
    expect(screen.getByRole('meter', { name: 'All trades' })).toHaveAttribute(
      'aria-valuenow',
      '70',
    );
    expect(screen.getByText('Projected: 15 Mar 2027')).toBeInTheDocument();
    const checks = screen.getByRole('list', { name: 'Checks that the result is real' });
    expect(within(checks).getAllByRole('listitem')).toHaveLength(2);
    expect(within(checks).getByText('Deflated Sharpe')).toBeInTheDocument();
    expect(within(checks).getByText('Not measured')).toBeInTheDocument();
    expect(screen.getByText('help verdict_outlook')).toBeInTheDocument();
  });

  it("shows the verdict at the count on today's figures, when each count is expected and the next close", () => {
    header();
    expect(screen.getByText("At 40, on today's figures: Not working.")).toBeInTheDocument();
    expect(
      screen.getByText(
        '40 out-of-sample ≈ 15 Mar 2027 · 100 trades ≈ 1 Feb 2027 · next closes 10 Nov 2026',
      ),
    ).toBeInTheDocument();
  });

  it('shows a test that does not apply as neutral, never a pass', () => {
    const evidence = momentum.verdict.evidence;
    if (!evidence) throw new Error('the fixture has evidence');
    header({
      ...momentum,
      verdict: {
        ...momentum.verdict,
        evidence: {
          ...evidence,
          checks: [
            {
              id: 'baselines',
              label: 'Lift against every baseline',
              value: 'no decoys declared',
              threshold: 'beats every baseline',
              status: 'not_applicable',
              level: 'promising',
            },
          ],
        },
      },
    });
    const checks = screen.getByRole('list', { name: 'Checks that the result is real' });
    expect(within(checks).getByText('Does not apply')).toBeInTheDocument();
    expect(within(checks).queryByText('Pass')).not.toBeInTheDocument();
  });

  it('says what a basis chosen among several was chosen on', () => {
    header({
      ...momentum,
      verdict: {
        ...momentum.verdict,
        basisWhy: 'chosen on in-sample lift: 15 d +3.1 pts, 31 d +2.7 pts',
      },
    });
    expect(
      screen.getByText('chosen on in-sample lift: 15 d +3.1 pts, 31 d +2.7 pts'),
    ).toBeInTheDocument();
  });

  it('names a short side, and says nothing for the usual long one', () => {
    header({ ...momentum, verdict: { ...momentum.verdict, side: 'short' } });
    expect(screen.getByText('Short')).toBeInTheDocument();
    cleanup();
    header(momentum);
    expect(screen.queryByText('Short')).not.toBeInTheDocument();
    expect(screen.queryByText('Long-short')).not.toBeInTheDocument();
  });

  it('gives the reason there is no date instead of a date', () => {
    const evidence = momentum.verdict.evidence;
    if (!evidence?.outlook) throw new Error('the fixture has an outlook');
    header({
      ...momentum,
      verdict: {
        ...momentum.verdict,
        evidence: {
          ...evidence,
          outlook: { ...evidence.outlook, projectionState: 'unprojectable', expectedBy: null },
        },
      },
    });
    expect(screen.getByText('Not projected: event schedule')).toBeInTheDocument();
  });

  it('has no outlook card for an edge with no evidence yet', () => {
    header(waiting);
    expect(
      screen.queryByRole('heading', { name: 'What would change the verdict' }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText('No official result yet').length).toBeGreaterThan(0);
    expect(screen.getByText('The effect vanished after 2005.')).toBeInTheDocument();
  });

  it("shows a copy's origin and labels, and offers the way back", async () => {
    const onBack = vi.fn();
    header({ ...mine, labels: ['followed_against_verdict'] }, onBack);
    expect(screen.getByText(/^Your edge · extends momentum_12_1/)).toBeInTheDocument();
    expect(screen.getByText('Followed against the verdict')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '← Setups' }));
    expect(onBack).toHaveBeenCalled();
  });
});
