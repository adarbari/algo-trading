import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ExplorePage } from './ExplorePage';

const widgets = vi.hoisted(() => ({ table: vi.fn(), compare: vi.fn(), options: vi.fn() }));

vi.mock('@/widgets/ticker-table', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    TickerTable: (props: Record<string, unknown>) => {
      widgets.table(props);
      return <Text>ticker table</Text>;
    },
  };
});
vi.mock('@/widgets/compare-panel', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    ComparePanel: (props: Record<string, unknown>) => {
      widgets.compare(props);
      return <Text>compare panel</Text>;
    },
  };
});
vi.mock('@/widgets/options-panel', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    OptionsPanel: (props: Record<string, unknown>) => {
      widgets.options(props);
      return <Text>options panel</Text>;
    },
  };
});

describe('ExplorePage', () => {
  it('reads its state from the search params, with defaults', () => {
    render(
      <ExplorePage
        search={{ sel: 'AAPL,MSFT', sort: '-feature.market_cap', lev: true }}
        onSearchChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Explore' })).toBeInTheDocument();
    expect(widgets.table).toHaveBeenLastCalledWith(
      expect.objectContaining({
        selected: ['AAPL', 'MSFT'],
        sort: { columnId: 'feature.market_cap', direction: 'desc' },
        filters: expect.objectContaining({ leveraged: true }) as unknown,
        columns: expect.arrayContaining(['rollup.iv30@v1.iv30']) as unknown,
      }),
    );
    expect(widgets.compare).toHaveBeenLastCalledWith(
      expect.objectContaining({ symbols: ['AAPL', 'MSFT'], range: '1Y' }),
    );
    expect(screen.getByRole('tab', { name: 'Compare' })).toHaveAttribute('aria-selected', 'true');
  });

  it('writes choices back as search params', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(
      <ExplorePage search={{ sel: 'AAPL,MSFT', focus: 'MSFT' }} onSearchChange={onSearchChange} />,
    );
    await user.click(screen.getByRole('tab', { name: 'Options' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ tab: 'options' });
    await user.click(screen.getByRole('button', { name: 'Remove MSFT from compare' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ sel: 'AAPL', focus: undefined });
    const table = widgets.table.mock.lastCall?.[0] as {
      onColumnsChange: (c: string[]) => void;
      onFocus: (s: string) => void;
    };
    table.onColumnsChange([]);
    expect(onSearchChange).toHaveBeenLastCalledWith({ cols: 'none' });
    table.onFocus('KO');
    expect(onSearchChange).toHaveBeenLastCalledWith({
      focus: 'KO',
      expiry: undefined,
      feature: undefined,
    });
  });

  it('shows the focused ticker in the detail tabs and the screener placeholder', () => {
    const { rerender } = render(
      <ExplorePage search={{ tab: 'options', focus: 'NVDA' }} onSearchChange={vi.fn()} />,
    );
    expect(widgets.options).toHaveBeenLastCalledWith(
      expect.objectContaining({ symbol: 'NVDA', view: 'simple', right: 'P', allStrikes: false }),
    );
    rerender(<ExplorePage search={{ tab: 'chart' }} onSearchChange={vi.fn()} />);
    expect(screen.getByText('No ticker chosen')).toBeInTheDocument();
    rerender(<ExplorePage search={{ tab: 'hits' }} onSearchChange={vi.fn()} />);
    expect(screen.getByText(/coming with the screener engine/)).toBeInTheDocument();
  });
});
