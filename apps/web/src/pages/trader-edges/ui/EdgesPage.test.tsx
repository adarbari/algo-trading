import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EdgesPage } from './EdgesPage';

vi.mock('@/widgets/edge-list', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EdgeList: () => <Text>list</Text> };
});
vi.mock('@/widgets/edge-detail', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EdgeDetail: ({ id }: { id: string }) => <Text>{`detail ${id}`}</Text> };
});

const onNew = vi.fn();

describe('EdgesPage', () => {
  it('shows its heading and the list when no edge is chosen', () => {
    render(<EdgesPage onSelect={vi.fn()} onEdit={vi.fn()} onNew={onNew} onClear={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Edges' })).toBeInTheDocument();
    expect(screen.getByText('list')).toBeInTheDocument();
    expect(screen.queryByText(/^detail/)).not.toBeInTheDocument();
  });

  it('opens the builder on a new edge', async () => {
    render(<EdgesPage onSelect={vi.fn()} onEdit={vi.fn()} onNew={onNew} onClear={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'New edge' }));
    expect(onNew).toHaveBeenCalled();
  });

  it('shows the chosen edge in place of the list', () => {
    render(
      <EdgesPage
        selected="momentum_12_1"
        onSelect={vi.fn()}
        onEdit={vi.fn()}
        onNew={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    expect(screen.getByText('detail momentum_12_1')).toBeInTheDocument();
    expect(screen.queryByText('list')).not.toBeInTheDocument();
  });
});
