import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SetupIdeas } from '@/entities/idea';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { IdeasHeading } from './IdeasHeading';

const hooks = vi.hoisted(() => ({ useSetupIdeas: vi.fn() }));
vi.mock('@/entities/idea', () => ({
  useSetupIdeas: hooks.useSetupIdeas,
  IDEA_TABS: [
    { id: 'stocks', label: 'Stocks' },
    { id: 'premium', label: 'Premium' },
  ],
}));
vi.mock('@/features/guide-help', () => ({ termHelp: () => null }));

const listed: SetupIdeas = {
  session: '2026-10-02',
  state: 'listed',
  total: 0,
  leftOut: [],
  groups: [],
  ideas: [],
};

describe('IdeasHeading', () => {
  beforeEach(() => {
    hooks.useSetupIdeas.mockReset();
  });

  it('names the session the ideas come from and offers the tabs', async () => {
    hooks.useSetupIdeas.mockReturnValue(fakeQuery<SetupIdeas>(listed));
    const onTabChange = vi.fn();
    const { container } = render(<IdeasHeading tab="stocks" onTabChange={onTabChange} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Ideas for Fri 2 Oct' })).toBeVisible();
    await userEvent.click(screen.getByRole('radio', { name: 'Premium' }));
    expect(onTabChange).toHaveBeenCalledWith('premium');
    await expectNoA11yViolations(container);
  });

  it('is plain "Ideas" until the session is known', () => {
    hooks.useSetupIdeas.mockReturnValue(fakeQuery<SetupIdeas>(undefined));
    render(<IdeasHeading tab="stocks" onTabChange={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Ideas' })).toBeVisible();
  });
});
