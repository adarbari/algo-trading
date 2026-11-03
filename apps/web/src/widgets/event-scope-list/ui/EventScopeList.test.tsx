import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { eventScopeFixture } from '@/entities/event-scope';
import { TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EventScopeList } from './EventScopeList';

const hooks = vi.hoisted(() => ({ useEventScope: vi.fn() }));
vi.mock('@/entities/event-scope', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEventScope: hooks.useEventScope,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text>,
  };
});

stubElementSize();

beforeEach(() => {
  hooks.useEventScope.mockReturnValue(fakeQuery(eventScopeFixture()));
});

const setup = () =>
  render(
    <TestQueryProvider>
      <EventScopeList />
    </TestQueryProvider>,
  );

describe('EventScopeList', () => {
  it('lists each name with its source, stale flag and share of big moves, and the strip counts', async () => {
    const { container } = setup();
    const strip = screen.getByLabelText('Scope summary');
    expect(within(strip).getByText('Listed names').parentElement).toHaveTextContent('2');
    expect(within(strip).getByText('Stale reviews').parentElement).toHaveTextContent('1');
    expect(within(strip).getByText(/Macro releases/).parentElement).toHaveTextContent('14');
    const table = screen.getByRole('grid', { name: 'Scope list' });
    expect(within(table).getByRole('row', { name: /AAPL/ })).toHaveTextContent('75%');
    expect(within(table).getByRole('row', { name: /AAPL/ })).toHaveTextContent('CURRENT');
    const msft = within(table).getByRole('row', { name: /MSFT/ });
    expect(msft).toHaveTextContent('STALE');
    expect(msft).toHaveTextContent('ana, 2026-10-25');
    expect(screen.getByText('help event_scope_stale')).toBeInTheDocument();
    expect(screen.getByRole('grid', { name: 'Removed names' })).toHaveTextContent('delisted');
    await expectNoA11yViolations(container);
  });

  it('opens the removal dialog for the row chosen', async () => {
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'Remove MSFT' }));
    expect(await screen.findByRole('dialog', { name: 'Remove MSFT' })).toBeInTheDocument();
  });

  it('names the symbols the session cannot resolve', () => {
    hooks.useEventScope.mockReturnValue(fakeQuery(eventScopeFixture({ unresolved: ['ZZZZ'] })));
    setup();
    expect(screen.getByText(/ZZZZ/)).toBeInTheDocument();
    expect(screen.getByText('help event_scope_unresolved')).toBeInTheDocument();
  });
});
