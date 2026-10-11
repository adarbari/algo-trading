import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Text } from '@algotrade/ui';
import { describe, expect, it, vi } from 'vitest';

import { edgeFixture } from '@/entities/edge';
import { stubElementSize } from '@/shared/lib/testing';

import { EdgeDetails } from './EdgeDetails';

vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

stubElementSize();

describe('EdgeDetails', () => {
  it('keeps the tests and the backtests behind a disclosure that loads on first open', async () => {
    render(<EdgeDetails edge={edgeFixture('momentum_12_1')} />);
    expect(screen.queryByText('EXPLORATORY')).not.toBeInTheDocument();
    await userEvent.click(screen.getByText('Details'));
    expect(await screen.findByText('Official result')).toBeInTheDocument();
    expect(screen.getByText('EXPLORATORY')).toBeInTheDocument();
    expect(screen.getByText('momentum_12_1: rollup (4 sessions)')).toBeInTheDocument();
    expect(screen.getByText('Not measured yet')).toBeInTheDocument();
    for (const id of ['verdict_criteria', 'baselines', 'edge_backtests', 'variants_tried']) {
      expect(screen.getAllByText(`help ${id}`).length).toBeGreaterThan(0);
    }
  });

  it('shows the sections the page composes in, once opened and not before', async () => {
    render(
      <EdgeDetails edge={edgeFixture('momentum_12_1')}>
        <Text>more details</Text>
      </EdgeDetails>,
    );
    expect(screen.queryByText('more details')).not.toBeInTheDocument();
    await userEvent.click(screen.getByText('Details'));
    expect(await screen.findByText('more details')).toBeInTheDocument();
  });
});
