import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EdgesPage } from './EdgesPage';

vi.mock('@/widgets/edge-list', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    EdgeList: ({ selected }: { selected: string | null }) => (
      <Text>{`list ${selected ?? 'none'}`}</Text>
    ),
  };
});
vi.mock('@/widgets/edge-detail', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EdgeDetail: ({ id }: { id: string | null }) => <Text>{`detail ${id ?? 'none'}`}</Text> };
});

describe('EdgesPage', () => {
  it('has its heading, the list and the chosen edge beside it', () => {
    render(<EdgesPage selected="momentum_12_1" onSelect={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Edges' })).toBeInTheDocument();
    expect(screen.getByText('list momentum_12_1')).toBeInTheDocument();
    expect(screen.getByText('detail momentum_12_1')).toBeInTheDocument();
  });
});
