import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ExplorePage } from './ExplorePage';

const widgets = vi.hoisted(() => ({
  table: vi.fn(),
  side: vi.fn(),
  compare: vi.fn(),
  options: vi.fn(),
  overview: vi.fn(),
  hits: vi.fn(),
}));

vi.mock('@/widgets/feature-table', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    FeatureTable: (props: Record<string, unknown>) => {
      (props['label'] === 'Tickers' ? widgets.table : widgets.side)(props);
      return <Text>{String(props['label'])}</Text>;
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
vi.mock('@/widgets/overview-panel', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    OverviewPanel: (props: Record<string, unknown>) => {
      widgets.overview(props);
      return <Text>overview panel</Text>;
    },
  };
});
vi.mock('@/widgets/screener-hits-panel', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    ScreenerHitsPanel: (props: Record<string, unknown>) => {
      widgets.hits(props);
      return <Text>screener hits</Text>;
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
        sortMode: 'server',
        selected: ['AAPL', 'MSFT'],
        sort: { columnId: 'feature.market_cap', direction: 'desc' },
        filters: expect.objectContaining({ leveraged: true }) as unknown,
        columns: expect.arrayContaining(['rollup.iv30@v1.iv30']) as unknown,
      }),
    );
    expect(widgets.compare).toHaveBeenLastCalledWith(
      expect.objectContaining({ symbols: ['AAPL', 'MSFT'], range: '1Y' }),
    );
    expect(widgets.side).toHaveBeenLastCalledWith(
      expect.objectContaining({
        sortMode: 'client',
        keys: ['AAPL', 'MSFT'],
        columns: expect.arrayContaining(['feature.market_cap']) as unknown,
      }),
    );
    expect(screen.getByRole('tab', { name: 'Compare' })).toHaveAttribute('aria-selected', 'true');
  });

  it('opens one ticker on its overview and goes back to the default in the URL', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(<ExplorePage search={{ sel: 'AAPL' }} onSearchChange={onSearchChange} />);
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(widgets.overview).toHaveBeenLastCalledWith(
      expect.objectContaining({ symbol: 'AAPL', fund: expect.anything() as unknown }),
    );
    await user.click(screen.getByRole('tab', { name: 'Compare' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ tab: 'compare' });
  });

  it('drops the tab from the URL when it is the default', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(
      <ExplorePage search={{ sel: 'AAPL', tab: 'options' }} onSearchChange={onSearchChange} />,
    );
    await user.click(screen.getByRole('tab', { name: 'Overview' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ tab: undefined });
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
      onRowActivate: (s: string) => void;
      onSelectedChange: (s: string[]) => void;
    };
    table.onColumnsChange([]);
    expect(onSearchChange).toHaveBeenLastCalledWith({ cols: 'none' });
    table.onRowActivate('KO');
    expect(onSearchChange).toHaveBeenLastCalledWith({
      focus: 'KO',
      expiry: undefined,
      feature: undefined,
    });
    table.onSelectedChange(['KO', 'AAPL', 'MSFT']);
    expect(onSearchChange).toHaveBeenLastCalledWith({ sel: 'AAPL,MSFT,KO' });
  });

  it('shows the focused ticker in the detail tabs, and its screener hits', () => {
    const { rerender } = render(
      <ExplorePage search={{ tab: 'options', focus: 'NVDA' }} onSearchChange={vi.fn()} />,
    );
    expect(widgets.options).toHaveBeenLastCalledWith(
      expect.objectContaining({ symbol: 'NVDA', view: 'simple', right: 'P', allStrikes: false }),
    );
    rerender(<ExplorePage search={{ tab: 'chart' }} onSearchChange={vi.fn()} />);
    expect(screen.getByText('No ticker chosen')).toBeInTheDocument();
    rerender(<ExplorePage search={{ tab: 'hits' }} onSearchChange={vi.fn()} />);
    expect(screen.getByText('No ticker chosen')).toBeInTheDocument();
    rerender(<ExplorePage search={{ tab: 'hits', focus: 'NVDA' }} onSearchChange={vi.fn()} />);
    expect(widgets.hits).toHaveBeenLastCalledWith({ symbol: 'NVDA' });
  });
});
