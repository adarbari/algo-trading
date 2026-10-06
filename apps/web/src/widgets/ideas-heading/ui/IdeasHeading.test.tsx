import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { IdeasData } from '@/entities/idea';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { IdeasHeading } from './IdeasHeading';

const hooks = vi.hoisted(() => ({ useIdeas: vi.fn() }));
vi.mock('@/entities/idea', () => ({ useIdeas: hooks.useIdeas }));

describe('IdeasHeading', () => {
  beforeEach(() => {
    hooks.useIdeas.mockReset();
  });

  it('names the session the ideas come from', async () => {
    const data: IdeasData = {
      session: '2026-10-02',
      total: 0,
      ideas: [],
      pausedTotal: 0,
      paused: [],
      screeners: [],
    };
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(data));
    const { container } = render(<IdeasHeading />);
    expect(screen.getByRole('heading', { level: 1, name: 'Ideas for Fri 2 Oct' })).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('is plain "Ideas" until the session is known', () => {
    hooks.useIdeas.mockReturnValue(fakeQuery<IdeasData>(undefined));
    render(<IdeasHeading />);
    expect(screen.getByRole('heading', { level: 1, name: 'Ideas' })).toBeVisible();
  });
});
