import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EdgesPage } from './EdgesPage';

vi.mock('@/widgets/setup-library', async () => {
  const { Text } = await import('@algotrade/ui');
  return { SetupLibrary: () => <Text>list</Text> };
});
vi.mock('./EdgePage', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EdgePage: ({ id }: { id: string }) => <Text>{`detail ${id}`}</Text> };
});

const onBuild = vi.fn();
const search = { search: {}, onSearchChange: vi.fn() };

describe('EdgesPage', () => {
  it('shows its heading and the list when no edge is chosen', () => {
    render(<EdgesPage onSelect={vi.fn()} onBuild={onBuild} onClear={vi.fn()} {...search} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Setups' })).toBeInTheDocument();
    expect(screen.getByText('list')).toBeInTheDocument();
    expect(screen.queryByText(/^detail/)).not.toBeInTheDocument();
  });

  it('opens the builder on a new edge', async () => {
    render(<EdgesPage onSelect={vi.fn()} onBuild={onBuild} onClear={vi.fn()} {...search} />);
    await userEvent.click(screen.getByRole('button', { name: 'Test your own idea' }));
    expect(onBuild).toHaveBeenCalledWith(null);
  });

  it('shows the chosen edge in place of the list', () => {
    render(
      <EdgesPage
        selected="momentum_12_1"
        onSelect={vi.fn()}
        onBuild={vi.fn()}
        onClear={vi.fn()}
        {...search}
      />,
    );
    expect(screen.getByText('detail momentum_12_1')).toBeInTheDocument();
    expect(screen.queryByText('list')).not.toBeInTheDocument();
  });
});
