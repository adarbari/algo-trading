import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { SessionStrip, type SessionStripItem } from './SessionStrip';

const ITEMS: SessionStripItem[] = [
  { label: 'Oct 20: Not run', tone: 'muted' },
  { label: 'Oct 21: Partial, 4 picked', tone: 'warning' },
  { label: 'Oct 22: Complete, 12 picked', tone: 'positive', current: true },
];

describe('SessionStrip', () => {
  it('is a named group with one button per session, oldest first, each named by its label', () => {
    render(<SessionStrip items={ITEMS} label="Last 3 sessions" />);
    expect(screen.getByRole('group', { name: 'Last 3 sessions' })).toBeInTheDocument();
    expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual(
      ITEMS.map((i) => i.label),
    );
  });

  it('draws each square in its tone and marks the current one', () => {
    render(<SessionStrip items={ITEMS} label="Last 3 sessions" />);
    const cells = screen.getAllByRole('button');
    expect(cells.map((c) => c.getAttribute('data-tone'))).toEqual(['muted', 'warning', 'positive']);
    expect(cells.map((c) => c.getAttribute('data-current'))).toEqual([null, null, 'true']);
  });

  it('writes the label of the focused or hovered square in one caption, and clears it', async () => {
    render(<SessionStrip items={ITEMS} label="Last 3 sessions" />);
    expect(screen.queryByText('Oct 20: Not run')).toBeNull();
    await userEvent.tab();
    expect(screen.getByText('Oct 20: Not run')).toBeInTheDocument();
    await userEvent.hover(screen.getAllByRole('button')[2] as HTMLElement);
    expect(screen.getByText('Oct 22: Complete, 12 picked')).toBeInTheDocument();
    expect(screen.queryByText('Oct 20: Not run')).toBeNull();
    await userEvent.unhover(screen.getAllByRole('button')[2] as HTMLElement);
    await userEvent.tab();
    await userEvent.tab();
    await userEvent.tab();
    expect(screen.queryByText(/Complete, 12 picked$/)).toBeNull();
  });

  it('a tap on a square opens its caption and a tap elsewhere closes it', async () => {
    render(<SessionStrip items={ITEMS} label="Last 3 sessions" />);
    await userEvent.click(screen.getAllByRole('button')[1] as HTMLElement);
    expect(screen.getByText('Oct 21: Partial, 4 picked')).toBeInTheDocument();
    await userEvent.click(document.body);
    expect(screen.queryByText('Oct 21: Partial, 4 picked')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<SessionStrip items={ITEMS} label="Last 3 sessions" />);
    await expectNoA11yViolations(container);
  });
});
