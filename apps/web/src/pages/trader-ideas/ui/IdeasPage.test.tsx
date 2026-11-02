import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { IdeasPage } from './IdeasPage';

const widgets = vi.hoisted(() => ({ top: vi.fn() }));

vi.mock('@/widgets/regime-strip', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    RegimeStrip: (props: { onOpen: () => void }) => (
      <Button onClick={props.onOpen}>regime strip</Button>
    ),
  };
});
vi.mock('@/widgets/paused-ideas', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    PausedIdeas: (props: {
      onOpen: (s: string, via: string) => void;
      onOpenScreener: (id: string) => void;
    }) => (
      <>
        <Button
          onClick={() => {
            props.onOpen('XOM', 'vrp');
          }}
        >
          paused
        </Button>
        <Button
          onClick={() => {
            props.onOpenScreener('liq');
          }}
        >
          paused screener
        </Button>
      </>
    ),
  };
});
vi.mock('@/widgets/ideas-heading', async () => {
  const { Heading, Button } = await import('@algotrade/ui');
  return {
    IdeasHeading: (props: { tab: string; onTabChange: (tab: 'premium') => void }) => (
      <>
        <Heading level={1}>Ideas for Fri 2 Oct</Heading>
        <Button
          onClick={() => {
            props.onTabChange('premium');
          }}
        >{`tab ${props.tab}`}</Button>
      </>
    ),
  };
});
vi.mock('@/widgets/setup-ideas', () => ({
  // the tab's Unproven section is what the page composes into the widget
  SetupIdeas: (props: { tab: string; unproven: React.ReactNode }) => <>{props.unproven}</>,
}));
vi.mock('@/widgets/top-ideas', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    TopIdeas: (props: {
      search: { f?: string };
      onSearchChange: (patch: { f: string }) => void;
      onCompare: (s: { sel: string; focus: string }) => void;
      onOpen: (s: string, via: string) => void;
      onScreeners: () => void;
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
          <Button onClick={props.onScreeners}>screeners</Button>
          <Button
            onClick={() => {
              props.onSearchChange({ f: 'decision:QUALIFIED' });
            }}
          >
            conviction
          </Button>
          <Button
            onClick={() => {
              props.onOpen('KO', 'liq');
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
  it('shows the ideas table alone and passes the search and navigation through', async () => {
    const user = userEvent.setup();
    const onCompare = vi.fn();
    const onOpen = vi.fn();
    const onSearchChange = vi.fn();
    const onScreeners = vi.fn();
    const onOpenRegime = vi.fn();
    const onOpenScreener = vi.fn();
    const onOpenEdge = vi.fn();
    const { container } = render(
      <IdeasPage
        search={{ f: 'earnings:..5s' }}
        onSearchChange={onSearchChange}
        onCompare={onCompare}
        onOpen={onOpen}
        onScreeners={onScreeners}
        onOpenScreener={onOpenScreener}
        onOpenRegime={onOpenRegime}
        onOpenEdge={onOpenEdge}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Ideas for Fri 2 Oct' })).toBeVisible();
    expect(widgets.top).toHaveBeenCalledWith(
      expect.objectContaining({ search: { f: 'earnings:..5s' } }),
    );
    await user.click(screen.getByRole('button', { name: 'tab stocks' }));
    expect(onSearchChange).toHaveBeenCalledWith({ tab: 'premium' });
    await user.click(screen.getByRole('button', { name: 'regime strip' }));
    expect(onOpenRegime).toHaveBeenCalledOnce();
    await user.click(screen.getByRole('button', { name: 'conviction' }));
    expect(onSearchChange).toHaveBeenCalledWith({ f: 'decision:QUALIFIED' });
    await user.click(screen.getByRole('button', { name: 'compare' }));
    expect(onCompare).toHaveBeenCalledWith({ sel: 'AAPL,MSFT', focus: 'AAPL' });
    await user.click(screen.getByRole('button', { name: 'open' }));
    expect(onOpen).toHaveBeenCalledWith('KO', 'liq');
    await user.click(screen.getByRole('button', { name: 'paused' }));
    expect(onOpen).toHaveBeenLastCalledWith('XOM', 'vrp');
    await user.click(screen.getByRole('button', { name: 'paused screener' }));
    expect(onOpenScreener).toHaveBeenLastCalledWith('liq');
    await user.click(screen.getByRole('button', { name: 'screeners' }));
    expect(onScreeners).toHaveBeenCalledOnce();
    await expectNoA11yViolations(container);
  });
});
