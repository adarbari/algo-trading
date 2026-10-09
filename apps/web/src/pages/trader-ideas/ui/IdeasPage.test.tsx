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
vi.mock('@/widgets/edge-signals', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    EdgeSignals: (props: {
      onOpen: (s: string, via: string) => void;
      onOpenEdge: (id: string) => void;
      onOpenEdges: () => void;
    }) => (
      <>
        <Button
          onClick={() => {
            props.onOpen('MSFT', 'drift');
          }}
        >
          signal
        </Button>
        <Button
          onClick={() => {
            props.onOpenEdge('drift');
          }}
        >
          signal edge
        </Button>
        <Button onClick={props.onOpenEdges}>edges</Button>
      </>
    ),
  };
});
vi.mock('@/widgets/ideas-heading', async () => {
  const { Heading } = await import('@algotrade/ui');
  return { IdeasHeading: () => <Heading level={1}>Ideas for Fri 2 Oct</Heading> };
});
vi.mock('@/widgets/top-ideas', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    TopIdeas: (props: {
      search: { view?: string };
      onSearchChange: (patch: { view: string }) => void;
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
              props.onSearchChange({ view: 'conviction' });
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
    const onOpenEdges = vi.fn();
    const { container } = render(
      <IdeasPage
        search={{ view: 'no-earnings' }}
        onSearchChange={onSearchChange}
        onCompare={onCompare}
        onOpen={onOpen}
        onScreeners={onScreeners}
        onOpenScreener={onOpenScreener}
        onOpenRegime={onOpenRegime}
        onOpenEdge={onOpenEdge}
        onOpenEdges={onOpenEdges}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Ideas for Fri 2 Oct' })).toBeVisible();
    expect(widgets.top).toHaveBeenCalledWith(
      expect.objectContaining({ search: { view: 'no-earnings' } }),
    );
    await user.click(screen.getByRole('button', { name: 'regime strip' }));
    expect(onOpenRegime).toHaveBeenCalledOnce();
    await user.click(screen.getByRole('button', { name: 'conviction' }));
    expect(onSearchChange).toHaveBeenCalledWith({ view: 'conviction' });
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
    await user.click(await screen.findByRole('button', { name: 'signal' }));
    expect(onOpen).toHaveBeenLastCalledWith('MSFT', 'drift');
    await user.click(screen.getByRole('button', { name: 'signal edge' }));
    expect(onOpenEdge).toHaveBeenCalledWith('drift');
    await user.click(screen.getByRole('button', { name: 'edges' }));
    expect(onOpenEdges).toHaveBeenCalledOnce();
    await expectNoA11yViolations(container);
  });
});
