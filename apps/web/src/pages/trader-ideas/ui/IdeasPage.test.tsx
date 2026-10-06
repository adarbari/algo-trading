import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { IdeasPage } from './IdeasPage';

const widgets = vi.hoisted(() => ({ ranking: vi.fn(), top: vi.fn() }));

vi.mock('@/widgets/screener-ranking', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    ScreenerRanking: (props: { onNewScreener: () => void }) => {
      widgets.ranking(props);
      return <Button onClick={props.onNewScreener}>new screener</Button>;
    },
  };
});
vi.mock('@/widgets/regime-strip', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    RegimeStrip: (props: { onOpen: () => void }) => (
      <Button onClick={props.onOpen}>regime strip</Button>
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
      onCompare: (s: { sel: string; focus: string }) => void;
      onOpen: (s: string) => void;
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
    const onNewScreener = vi.fn();
    const onScreeners = vi.fn();
    const onOpenRegime = vi.fn();
    const { container } = render(
      <IdeasPage
        onCompare={onCompare}
        onOpen={onOpen}
        onNewScreener={onNewScreener}
        onScreeners={onScreeners}
        onOpenScreener={vi.fn()}
        onOpenRegime={onOpenRegime}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Ideas for Fri 2 Oct' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'regime strip' }));
    expect(onOpenRegime).toHaveBeenCalledOnce();
    await user.click(screen.getByRole('button', { name: 'new screener' }));
    expect(onNewScreener).toHaveBeenCalledOnce();
    await user.click(screen.getByRole('button', { name: 'compare' }));
    expect(onCompare).toHaveBeenCalledWith({ sel: 'AAPL,MSFT', focus: 'AAPL' });
    await user.click(screen.getByRole('button', { name: 'open' }));
    expect(onOpen).toHaveBeenCalledWith('KO');
    await user.click(screen.getByRole('button', { name: 'screeners' }));
    expect(onScreeners).toHaveBeenCalledOnce();
    await expectNoA11yViolations(container);
  });
});
