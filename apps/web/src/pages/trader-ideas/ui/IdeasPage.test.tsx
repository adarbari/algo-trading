import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { IdeasPage } from './IdeasPage';

const widgets = vi.hoisted(() => ({ ranking: vi.fn(), top: vi.fn() }));

vi.mock('@/widgets/screener-ranking', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    ScreenerRanking: () => {
      widgets.ranking();
      return <Text>screener ranking</Text>;
    },
  };
});
vi.mock('@/widgets/top-ideas', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    TopIdeas: (props: {
      onCompare: (s: { sel: string; focus: string }) => void;
      onOpen: (s: string) => void;
    }) => {
      widgets.top(props);
      return (
        <>
          <Button
            onClick={() => {
              props.onCompare({ sel: 'AAPL,MSFT', focus: 'AAPL' });
            }}
          >
            compare
          </Button>
          <Button
            onClick={() => {
              props.onOpen('KO');
            }}
          >
            open
          </Button>
        </>
      );
    },
  };
});

describe('IdeasPage', () => {
  it('shows the screener ranking beside the top ideas and passes navigation through', async () => {
    const user = userEvent.setup();
    const onCompare = vi.fn();
    const onOpen = vi.fn();
    render(<IdeasPage onCompare={onCompare} onOpen={onOpen} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Ideas' })).toBeInTheDocument();
    expect(screen.getByText('screener ranking')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'compare' }));
    expect(onCompare).toHaveBeenCalledWith({ sel: 'AAPL,MSFT', focus: 'AAPL' });
    await user.click(screen.getByRole('button', { name: 'open' }));
    expect(onOpen).toHaveBeenCalledWith('KO');
  });
});
