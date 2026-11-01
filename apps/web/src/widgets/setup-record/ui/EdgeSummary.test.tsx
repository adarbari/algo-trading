import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { edgeFixture } from '@/entities/edge';

import { EdgeSummary } from './EdgeSummary';

vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
    Labelled: ({ text, help }: { text: string; help: string }) => (
      <Text>{`${text} help ${help}`}</Text>
    ),
  };
});

const verdict = edgeFixture('momentum_12_1').verdict;

describe('EdgeSummary', () => {
  it('shows the out-of-sample strip with what is needed and the one line with its basis and variants', () => {
    render(<EdgeSummary verdict={verdict} />);
    const strip = screen.getByRole('region', { name: 'Out-of-sample result' });
    expect(within(strip).getByText('57%')).toBeInTheDocument();
    expect(within(strip).getByText('+5.0 pts')).toBeInTheDocument();
    expect(within(strip).getByText('40 needed')).toBeInTheDocument();
    expect(within(strip).getByText('96%')).toBeInTheDocument();
    expect(
      screen.getByText(/momentum_12_1, 20 trading days · 3 variants tried/),
    ).toBeInTheDocument();
  });

  it('leaves the line out and reads missing figures as missing when there is no result', () => {
    render(
      <EdgeSummary
        verdict={{
          ...verdict,
          winRate: null,
          baseRate: null,
          oosTrades: null,
          evidence: null,
          robustness: null,
        }}
      />,
    );
    const strip = screen.getByRole('region', { name: 'Out-of-sample result' });
    expect(within(strip).getAllByText('—').length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText(/variants tried/)).not.toBeInTheDocument();
  });
});
