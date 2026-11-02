import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ExplorePage } from './ExplorePage';

const widgets = vi.hoisted(() => ({
  side: vi.fn(),
  compare: vi.fn(),
  options: vi.fn(),
  overview: vi.fn(),
  hits: vi.fn(),
  why: vi.fn(),
  universe: vi.fn(),
}));

vi.mock('./UniverseTable', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    UniverseTable: (props: Record<string, unknown>) => {
      widgets.universe(props);
      return <Text>universe table</Text>;
    },
  };
});
vi.mock('@/widgets/feature-table', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    FeatureTable: (props: Record<string, unknown>) => {
      widgets.side(props);
      return (
        <>
          <Text>{String(props['label'])}</Text>
          {props['header'] as React.ReactNode}
        </>
      );
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
vi.mock('@/widgets/ticker-stands', async () => {
  const { Text } = await import('@algotrade/ui');
  return { TickerStands: ({ symbol }: { symbol: string }) => <Text>{`stands ${symbol}`}</Text> };
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
const viewer = vi.hoisted(() => ({ role: 'admin' }));
vi.mock('@/entities/viewer', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useViewer: () => ({ data: { role: viewer.role } }),
}));
vi.mock('@/widgets/option-grid', async () => {
  const { Text } = await import('@algotrade/ui');
  return { OptionGrid: ({ symbol }: { symbol: string }) => <Text>{`option grid ${symbol}`}</Text> };
});
vi.mock('@/widgets/option-calculators', async () => {
  const { Button, Text } = await import('@algotrade/ui');
  const { useState } = await import('react');
  return {
    RollCalculator: ({ symbol, onOpenCalls }: { symbol: string; onOpenCalls: () => void }) => (
      <>
        <Text>{`roll calculator ${symbol}`}</Text>
        <Button onClick={onOpenCalls}>Open calls</Button>
      </>
    ),
    // Keeps what it first mounted with, as the real one keeps the typed form and its result.
    CallsCalculator: function Calls({ symbol }: { symbol: string }) {
      const [typedFor] = useState(symbol);
      return (
        <>
          <Text>{`calls calculator ${symbol}`}</Text>
          <Text>{`typed for ${typedFor}`}</Text>
        </>
      );
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
    await waitFor(
      () => {
        expect(widgets.compare).toHaveBeenLastCalledWith(
          expect.objectContaining({ symbols: ['AAPL', 'MSFT'], range: '1Y' }),
        );
      },
      { timeout: 5000 },
    );
    await waitFor(
      () => {
        expect(widgets.side).toHaveBeenLastCalledWith(
          expect.objectContaining({
            sortMode: 'client',
            keys: ['AAPL', 'MSFT'],
            columns: expect.arrayContaining(['feature.market_cap']) as unknown,
          }),
        );
      },
      { timeout: 5000 },
    );
    expect(widgets.overview).not.toHaveBeenCalled();
  });

  it('opens one ticker on its overview, with no Compare tab', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(page({ sel: 'AAPL' }, onSearchChange));
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('tab', { name: 'Compare' })).toBeNull();
    expect(screen.queryByRole('tab', { name: 'Why it is an idea' })).toBeNull();
    await waitFor(
      () => {
        expect(widgets.overview).toHaveBeenLastCalledWith(
          expect.objectContaining({ symbol: 'AAPL', fund: expect.anything() as unknown }),
        );
      },
      { timeout: 5000 },
    );
    await user.click(screen.getByRole('tab', { name: 'Options' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ tab: 'options' });
  });

  it('shows a trader the derived option grid and an admin the raw chain', async () => {
    viewer.role = 'trader';
    const { unmount } = render(page({ sel: 'AAPL', tab: 'options' }));
    expect(await screen.findByText('option grid AAPL', {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByText('options panel')).not.toBeInTheDocument();
    unmount();
    viewer.role = 'admin';
    render(page({ sel: 'AAPL', tab: 'options' }));
    expect(await screen.findByText('options panel', {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it('shows the option calculators to a trader and an admin, and Roll links to Calls', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    for (const role of ['trader', 'admin']) {
      viewer.role = role;
      const { unmount } = render(page({ sel: 'AAPL', tab: 'roll' }, onSearchChange));
      expect(await screen.findByText('roll calculator AAPL', {}, { timeout: 5000 })).toBeVisible();
      unmount();
    }
    render(page({ sel: 'AAPL', tab: 'roll' }, onSearchChange));
    await user.click(await screen.findByRole('button', { name: 'Open calls' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ tab: 'calls' });
    cleanup();
    render(page({ sel: 'AAPL', tab: 'calls' }));
    expect(await screen.findByText('calls calculator AAPL', {}, { timeout: 5000 })).toBeVisible();
  });

  it('starts a calculator afresh when another ticker comes into focus', async () => {
    const { rerender } = render(page({ sel: 'AAPL,MSFT', focus: 'AAPL', tab: 'calls' }));
    expect(await screen.findByText('typed for AAPL', {}, { timeout: 5000 })).toBeVisible();
    rerender(page({ sel: 'AAPL,MSFT', focus: 'MSFT', tab: 'calls' }));
    expect(await screen.findByText('typed for MSFT')).toBeVisible();
    expect(screen.queryByText('typed for AAPL')).toBeNull();
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
    await waitFor(
      () => {
        expect(widgets.options).toHaveBeenLastCalledWith(
          expect.objectContaining({
            symbol: 'NVDA',
            view: 'simple',
            right: 'P',
            allStrikes: false,
          }),
        );
      },
      { timeout: 5000 },
    );
  });

  it('shows Why it is an idea only when Ideas named the screener, for that screener', async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    render(page({ sel: 'AAPL', focus: 'AAPL', via: 'vrp', tab: 'why' }, onSearchChange));
    expect(screen.getByRole('tab', { name: 'Why it is an idea' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await waitFor(
      () => {
        expect(widgets.why).toHaveBeenLastCalledWith(
          expect.objectContaining({ symbol: 'AAPL', screenerId: 'vrp' }),
        );
      },
      { timeout: 5000 },
    );
    await user.click(screen.getByRole('tab', { name: 'Overview' }));
    expect(onSearchChange).toHaveBeenLastCalledWith({ tab: 'overview' });
  });

  it('falls back to the overview when the Why tab is asked for without a screener', () => {
    render(page({ sel: 'AAPL', tab: 'why' }));
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
  });

  it('shows the screener hits of the focused ticker', async () => {
    render(page({ tab: 'hits', focus: 'NVDA' }));
    await waitFor(
      () => {
        expect(widgets.hits).toHaveBeenLastCalledWith(
          expect.objectContaining({
            symbol: 'NVDA',
            onOpenScreener: expect.any(Function) as unknown,
          }),
        );
      },
      { timeout: 5000 },
    );
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
      'Roll a put',
      'Calls on shares',
      'Features',
      'Financials',
      'Events',
      'Screener hits',
      'Why it is an idea',
    ]);
  });

  it('shows the universe table when no ticker is open, with the URL filters and its actions', async () => {
    const onSearchChange = vi.fn();
    render(page({ f: 'sector:Technology', dims: 'feature.market_cap' }, onSearchChange));
    expect(await screen.findByText('universe table')).toBeInTheDocument();
    expect(screen.queryByRole('tablist', { name: 'Open tickers' })).toBeNull();
    const props = widgets.universe.mock.lastCall?.[0] as {
      f: string;
      columns: string[];
      onFilterChange: (f: string | undefined) => void;
      onColumnsChange: (dims: string | undefined) => void;
      onOpen: (symbol: string) => void;
      onCompare: (symbols: string[]) => void;
    };
    expect(props.f).toBe('sector:Technology');
    expect(props.columns).toEqual(['feature.market_cap']);
    props.onFilterChange(undefined);
    expect(onSearchChange).toHaveBeenLastCalledWith({ f: undefined });
    props.onColumnsChange('feature.close');
    expect(onSearchChange).toHaveBeenLastCalledWith({ dims: 'feature.close' });
    props.onOpen('KO');
    expect(onSearchChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ sel: 'KO', focus: 'KO' }),
    );
    props.onCompare(['AAPL', 'MSFT']);
    expect(onSearchChange).toHaveBeenLastCalledWith({
      sel: 'AAPL,MSFT',
      focus: undefined,
      tab: 'compare',
    });
    props.onCompare(['AAPL']);
    expect(onSearchChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ sel: 'AAPL', focus: 'AAPL' }),
    );
  });
});
