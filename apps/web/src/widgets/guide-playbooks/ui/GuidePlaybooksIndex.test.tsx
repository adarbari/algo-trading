import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuidePlaybooksIndex } from './GuidePlaybooksIndex';

const hooks = vi.hoisted(() => ({ useGuideIndex: vi.fn(), useGuidePlaybook: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
  useGuidePlaybook: hooks.useGuidePlaybook,
}));

const index = {
  sections: [
    { id: 'playbooks', title: 'Playbooks', purpose: 'One page per site screen.', entries: 3 },
  ],
  families: [
    {
      id: 'breakouts',
      title: 'Breakouts',
      playbooks: [
        { id: 'range_breakout', name: 'Range breakout' },
        { id: 'breakout', name: 'Breakout' },
      ],
    },
    { id: 'income', title: 'Option income', playbooks: [{ id: 'vrp_scanner', name: 'VRP' }] },
  ],
};

const summaries: Record<string, string | null> = {
  range_breakout: 'Finds squeezes before the move.',
  breakout: 'Finds shares breaking out today.',
  vrp_scanner: null,
};

beforeEach(() => {
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
  hooks.useGuidePlaybook.mockImplementation((id: string) => {
    const text = summaries[id];
    return fakeQuery({ prose: text ? { summary: { segments: [{ text }] } } : null });
  });
});

describe('GuidePlaybooksIndex', () => {
  it('lists the families in the server’s order, each playbook linked with its summary', () => {
    render(<GuidePlaybooksIndex />);
    expect(screen.getByRole('heading', { level: 1, name: 'Playbooks' })).toBeInTheDocument();
    expect(screen.getByText('One page per site screen.')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Breakouts',
      'Option income',
    ]);
    const breakouts = within(screen.getByRole('region', { name: 'Breakouts' }));
    expect(
      breakouts.getAllByRole('link').map((l) => [l.textContent, l.getAttribute('href')]),
    ).toEqual([
      ['Range breakout', '/guide/playbooks/range_breakout'],
      ['Breakout', '/guide/playbooks/breakout'],
    ]);
    expect(breakouts.getByText('Finds shares breaking out today.')).toBeInTheDocument();
  });

  it('lists a playbook without prose by its name alone', () => {
    render(<GuidePlaybooksIndex />);
    const income = within(screen.getByRole('region', { name: 'Option income' }));
    expect(income.getByRole('link', { name: 'VRP' })).toBeInTheDocument();
    expect(income.getAllByText(/./)).toHaveLength(2); // heading and link only
  });

  it('shows loading, an error with a retry, and no playbooks', async () => {
    hooks.useGuideIndex.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuidePlaybooksIndex />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideIndex.mockReturnValue(failed);
    rerender(<GuidePlaybooksIndex />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideIndex.mockReturnValue(fakeQuery({ sections: [], families: [] }));
    rerender(<GuidePlaybooksIndex />);
    expect(screen.getByText('The Guide has no playbooks.')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuidePlaybooksIndex />);
    await expectNoA11yViolations(container);
  });
});
