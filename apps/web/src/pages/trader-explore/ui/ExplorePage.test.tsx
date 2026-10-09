import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ExplorePage } from './ExplorePage';

const widgets = vi.hoisted(() => ({
  search: vi.fn(),
  side: vi.fn(),
  compare: vi.fn(),
  options: vi.fn(),
  overview: vi.fn(),
  hits: vi.fn(),
  why: vi.fn(),
}));

vi.mock('@/features/ticker-search', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    TickerSearch: (props: Record<string, unknown>) => {
      widgets.search(props);
      return <Text>ticker search</Text>;
    },
  };
});
vi.mock('@/widgets/feature-table', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    FeatureTable: (props: Record<string, unknown>) => {
      widgets.side(props);
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
    WhyIdeaPanel: (props: Record<string, unknown>) => {
      widgets.why(props);
      return <Text>why panel</Text>;
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

const page = (search: Parameters<typeof ExplorePage>[0]['search'], onSearchChange = vi.fn()) => (
  <ExplorePage search={search} onSearchChange={onSearchChange} onOpenScreener={vi.fn()} />
);

const tickerTabs = () =>
  within(screen.getByRole('tablist', { name: 'Open tickers' }))
    .getAllByRole('tab')
    .map((t) => t.textContent);

describe('ExplorePage', () => {
  it('opens a set of tickers as tabs, on the comparison, only the selected tab mounted', async () => {
    render(page({ sel: 'AAPL,MSFT' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Explore' })).toBeInTheDocument();
    expect(tickerTabs()).toEqual(['AAPL', 'MSFT']);
    expect(screen.getByRole('tab', { name: 'AAPL' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Compare' })).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => {
      expect(widgets.compare).toHaveBeenLastCalledWith(
        expect.objectContaining({ symbols: ['AAPL', 'MSFT'], range: '1Y' }),
      );
    });
    await waitFor(() => {
      expect(widgets.side).toHaveBeenLastCalledWith(
        expect.objectContaining({
          sortMode: 'client',
          keys: ['AAPL', 'MSFT'],
          columns: expect.arrayContaining(['feature.market_cap']) as unknown,
        }),
      );
    });
    expect(widgets.overview).not.toHaveBeenCalled();
    expect(widgets.search).toHaveBeenLastCalledWith(
      expect.objectContaining({ focusKey: '/', chosen: ['AAPL', 'MSFT'] }),
    );
  });

  it('opens one ticker on its overview, with no Compare tab', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(page({ sel: 'AAPL' }, onSearchChange));
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('tab', { name: 'Compare' })).toBeNull();
    expect(screen.queryByRole('tab', { name: 'Why it is an idea' })).toBeNull();
    await waitFor(() => {
      expect(widgets.overview).toHaveBeenLastCalledWith(
        expect.objectContaining({ symbol: 'AAPL', fund: expect.anything() as unknown }),
      );
    });
    await user.click(screen.getByRole('tab', { name: 'Options' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ tab: 'options' });
  });

  it('adds a searched ticker as a tab and selects it on its overview', () => {
    const onSearchChange = vi.fn();
    render(page({ sel: 'AAPL', tab: 'options' }, onSearchChange));
    const props = widgets.search.mock.lastCall?.[0] as { onChoose: (s: string) => void };
    props.onChoose('NVDA');
    expect(onSearchChange).toHaveBeenLastCalledWith({
      sel: 'AAPL,NVDA',
      focus: 'NVDA',
      tab: undefined,
      expiry: undefined,
      feature: undefined,
      via: undefined,
    });
  });

  it('chooses and closes tabs through the URL', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(page({ sel: 'AAPL,MSFT,KO', focus: 'MSFT', tab: 'options' }, onSearchChange));
    await user.click(screen.getByRole('tab', { name: 'KO' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({
      sel: 'AAPL,MSFT,KO',
      focus: 'KO',
      expiry: undefined,
      feature: undefined,
      via: undefined,
    });
    await user.click(screen.getByRole('button', { name: 'Close KO', hidden: true }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ sel: 'AAPL,MSFT', focus: 'MSFT' });
    await user.click(screen.getByRole('button', { name: 'Close MSFT', hidden: true }));
    expect(onSearchChange).toHaveBeenLastCalledWith({
      sel: 'AAPL,KO',
      focus: 'KO',
      expiry: undefined,
      feature: undefined,
      via: undefined,
    });
  });

  it('a focus that is not open yet opens its own tab', async () => {
    render(page({ sel: 'AAPL', focus: 'NVDA', tab: 'options' }));
    expect(tickerTabs()).toEqual(['AAPL', 'NVDA']);
    await waitFor(() => {
      expect(widgets.options).toHaveBeenLastCalledWith(
        expect.objectContaining({ symbol: 'NVDA', view: 'simple', right: 'P', allStrikes: false }),
      );
    });
  });

  it('shows Why it is an idea only when Ideas named the screener, for that screener', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(page({ sel: 'AAPL', focus: 'AAPL', via: 'vrp', tab: 'why' }, onSearchChange));
    expect(screen.getByRole('tab', { name: 'Why it is an idea' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await waitFor(() => {
      expect(widgets.why).toHaveBeenLastCalledWith(
        expect.objectContaining({ symbol: 'AAPL', screenerId: 'vrp' }),
      );
    });
    await user.click(screen.getByRole('tab', { name: 'Overview' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ tab: 'overview' });
  });

  it('falls back to the overview when the Why tab is asked for without a screener', () => {
    render(page({ sel: 'AAPL', tab: 'why' }));
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
  });

  it('shows the screener hits of the focused ticker', async () => {
    render(page({ tab: 'hits', focus: 'NVDA' }));
    await waitFor(() => {
      expect(widgets.hits).toHaveBeenLastCalledWith(
        expect.objectContaining({
          symbol: 'NVDA',
          onOpenScreener: expect.any(Function) as unknown,
        }),
      );
    });
  });

  it('has no Field guide tab (field help is the Guide, from each help button)', () => {
    render(page({ sel: 'AAPL,MSFT', via: 'vrp', focus: 'AAPL' }));
    const view = screen.getByRole('tablist', { name: 'View' });
    expect(
      within(view)
        .getAllByRole('tab')
        .map((t) => t.textContent),
    ).toEqual([
      'Overview',
      'Compare',
      'Chart',
      'Options',
      'Features',
      'Events',
      'Screener hits',
      'Why it is an idea',
    ]);
  });

  it('asks for a ticker when none is open', () => {
    render(page({}));
    expect(screen.getByText('No ticker open')).toBeInTheDocument();
    expect(screen.queryByRole('tablist', { name: 'Open tickers' })).toBeNull();
  });
});
