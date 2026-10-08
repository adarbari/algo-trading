import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { NO_IDEAS, type IdeasData } from '@/entities/idea';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { PausedIdeas } from './PausedIdeas';

const hooks = vi.hoisted(() => ({ useIdeas: vi.fn() }));
vi.mock('@/entities/idea', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useIdeas: hooks.useIdeas,
}));

const paused = (symbol: string | null, reason: string) => ({
  instrumentId: `id-${symbol ?? 'x'}`,
  symbol,
  screenerId: 'vrp',
  screenerName: 'VRP scanner',
  score: 70,
  reason,
  regime: 'STRESS',
});
const data = (over: Partial<IdeasData>): IdeasData => ({
  ...NO_IDEAS,
  session: '2026-10-02',
  ...over,
});

beforeEach(() => {
  hooks.useIdeas.mockReset();
});

describe('PausedIdeas', () => {
  it('lists the paused picks with their screener and reason, collapsed until opened', async () => {
    hooks.useIdeas.mockReturnValue(
      fakeQuery<IdeasData>(
        data({
          pausedTotal: 2,
          paused: [paused('XOM', 'regime=STRESS: vrp pauses in STRESS'), paused(null, '')],
        }),
      ),
    );
    const onOpen = vi.fn();
    const onOpenScreener = vi.fn();
    const { container } = render(<PausedIdeas onOpen={onOpen} onOpenScreener={onOpenScreener} />);
    const toggle = screen.getByRole('button', { name: /Paused by regime/ });
    expect(toggle).toHaveTextContent('(2)');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.setup().click(toggle);
    expect(screen.getByText('regime=STRESS: vrp pauses in STRESS')).toBeVisible();
    expect(screen.getAllByText('VRP scanner')).toHaveLength(2);
    expect(screen.getByText('Paused by the regime gate')).toBeVisible(); // no stored reason
    await userEvent.setup().click(screen.getByRole('button', { name: 'XOM' }));
    expect(onOpen).toHaveBeenCalledWith('XOM', 'vrp');
    await userEvent
      .setup()
      .click(screen.getAllByRole('button', { name: 'VRP scanner' }).at(0) as HTMLElement);
    expect(onOpenScreener).toHaveBeenCalledWith('vrp');
    await expectNoA11yViolations(container);
  });

  it('says how many more there are than the rows it has', async () => {
    hooks.useIdeas.mockReturnValue(
      fakeQuery<IdeasData>(
        data({ pausedTotal: 5, paused: [paused('XOM', 'regime=STRESS: vrp pauses in STRESS')] }),
      ),
    );
    render(<PausedIdeas onOpen={vi.fn()} onOpenScreener={vi.fn()} />);
    await userEvent.setup().click(screen.getByRole('button', { name: /Paused by regime/ }));
    expect(screen.getByText('4 more not listed here')).toBeVisible();
  });

  it('shows nothing while nothing is paused or while loading', () => {
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(data({})));
    const { container, rerender } = render(
      <PausedIdeas onOpen={vi.fn()} onOpenScreener={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(undefined));
    rerender(<PausedIdeas onOpen={vi.fn()} onOpenScreener={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('says so when the read failed', () => {
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(undefined, { isError: true }));
    render(<PausedIdeas onOpen={vi.fn()} onOpenScreener={vi.fn()} />);
    expect(screen.getByText('The ideas paused by the regime could not be read.')).toBeVisible();
  });
});
