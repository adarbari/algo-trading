import { ToastProvider } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { IdeasData } from '@/entities/idea';
import { TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { ScreenerRanking } from './ScreenerRanking';

const hooks = vi.hoisted(() => ({ useIdeas: vi.fn() }));
vi.mock('@/entities/idea', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useIdeas: hooks.useIdeas,
}));

const data: IdeasData = {
  session: '2026-10-02',
  total: 2,
  ideas: [],
  screeners: [
    {
      id: 'vrp-scanner',
      name: 'VRP scanner',
      user: 'abhinav',
      version: 3,
      qualified: 14,
      top: [
        { symbol: 'AAPL', score: 84 },
        { symbol: 'MSFT', score: 79 },
      ],
    },
    { id: 'near-low', name: 'near-low', user: 'abhinav', version: null, qualified: 0, top: [] },
  ],
};

const onNew = vi.fn();

function setup() {
  return render(
    <ToastProvider>
      <TestQueryProvider>
        <ScreenerRanking onNewScreener={onNew} />
      </TestQueryProvider>
    </ToastProvider>,
  );
}

beforeEach(() => {
  hooks.useIdeas.mockReturnValue(fakeQuery(data));
});

describe('ScreenerRanking', () => {
  it('lists the screeners in priority order with their finds', async () => {
    const { container } = setup();
    expect(screen.getByRole('heading', { name: 'Your screeners' })).toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('VRP scanner');
    expect(items[0]).toHaveTextContent('AAPL 84 · MSFT 79');
    expect(items[0]).toHaveTextContent('14');
    expect(items[1]).toHaveTextContent('No picks');
    await expectNoA11yViolations(container);
  });

  it('shows loading, empty and error states', async () => {
    hooks.useIdeas.mockReturnValue(fakeQuery(undefined));
    const { unmount, container } = setup();
    expect(screen.getByText('Loading screeners…')).toBeInTheDocument();
    await expectNoA11yViolations(container);
    unmount();

    hooks.useIdeas.mockReturnValue(fakeQuery({ ...data, screeners: [] }));
    const empty = setup();
    expect(screen.getByText(/No screener has run yet/)).toBeInTheDocument();
    await expectNoA11yViolations(empty.container);
    empty.unmount();

    const query = fakeQuery<IdeasData>(undefined, { isError: true, error: new Error('x') });
    hooks.useIdeas.mockReturnValue(query);
    const failed = setup();
    expect(screen.getByText('The screeners failed to load.')).toBeInTheDocument();
    await expectNoA11yViolations(failed.container);
  });
});
