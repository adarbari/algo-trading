import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PEOPLE_FIXTURE } from '@/entities/user-registry';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { UserList } from './UserList';

const hooks = vi.hoisted(() => ({ useUserRegistry: vi.fn() }));
vi.mock('@/entities/user-registry', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useUserRegistry: hooks.useUserRegistry,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

stubElementSize();

beforeEach(() => {
  hooks.useUserRegistry.mockReturnValue(fakeQuery({ people: PEOPLE_FIXTURE }));
});

describe('UserList', () => {
  it('counts people without the scheduled user and lists every declared user with its help', async () => {
    const { container } = render(<UserList />);
    const strip = screen.getByLabelText('People summary');
    expect(within(strip).getByText('People').parentElement).toHaveTextContent('2');
    expect(within(strip).getByText('Admins').parentElement).toHaveTextContent('1');
    const table = screen.getByRole('grid', { name: 'People' });
    expect(within(table).getByRole('row', { name: /ana/ })).toHaveTextContent('Admin');
    expect(within(table).getByRole('row', { name: /tom/ })).toHaveTextContent('Trader');
    expect(within(table).getByRole('row', { name: /site/ })).toBeInTheDocument();
    expect(screen.getByText('help user_licences')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
