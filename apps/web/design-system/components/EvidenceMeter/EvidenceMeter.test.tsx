import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { EvidenceMeter } from './EvidenceMeter';

const MILESTONES = [
  { at: 10, label: 'first read' },
  { at: 40, label: 'decision' },
  { at: 25, label: 'checkpoint' },
];

describe('EvidenceMeter', () => {
  it('is a named meter reading "5 of 40"', () => {
    render(<EvidenceMeter label="Trades" value={5} max={40} />);
    const meter = screen.getByRole('meter', { name: 'Trades' });
    expect(meter).toHaveAttribute('aria-valuemin', '0');
    expect(meter).toHaveAttribute('aria-valuemax', '40');
    expect(meter).toHaveAttribute('aria-valuenow', '5');
    expect(meter).toHaveAttribute('aria-valuetext', '5 of 40');
    expect(meter).toHaveStyle({ '--pos': '12.5%' });
  });

  it('clamps the fill to the track and keeps the real reading', () => {
    const { rerender } = render(<EvidenceMeter label="Trades" value={52} max={40} />);
    expect(screen.getByRole('meter')).toHaveStyle({ '--pos': '100%' });
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '40');
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '52 of 40');
    rerender(<EvidenceMeter label="Trades" value={-3} max={40} />);
    expect(screen.getByRole('meter')).toHaveStyle({ '--pos': '0%' });
  });

  it('marks ticks at or below the value as reached, in order, and tells screen readers', () => {
    const { container } = render(
      <EvidenceMeter
        label="Trades"
        value={25}
        max={40}
        milestones={MILESTONES}
        caption="By 12 Nov."
      />,
    );
    const ticks = [...container.querySelectorAll('[data-reached], span[style*="--at"]')].filter(
      (el) => el.getAttribute('style')?.includes('--at') && !el.textContent,
    );
    expect(ticks.map((t) => t.hasAttribute('data-reached'))).toEqual([true, true, false]);
    expect(screen.getByText('10 first read')).toBeInTheDocument();
    expect(screen.getByRole('meter')).toHaveAccessibleDescription(
      'By 12 Nov. Milestones: first read at 10, reached; checkpoint at 25, reached; decision at 40, not yet reached.',
    );
  });

  it('shows unknown as a dashed empty track with the reason, never a zero', () => {
    const { container } = render(
      <EvidenceMeter
        label="Trades"
        value={0}
        max={40}
        state="unknown"
        unknownLabel="No trades yet"
      />,
    );
    expect(screen.queryByRole('meter')).toBeNull();
    expect(screen.getByRole('img')).toHaveAccessibleName('Trades: unknown. No trades yet');
    expect(screen.getByText('No trades yet')).toBeInTheDocument();
    expect(container.querySelector('[data-unknown]')).not.toBeNull();
    expect(screen.queryByText('0 of 40')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container, rerender } = render(
      <EvidenceMeter
        label="Trades"
        value={12}
        max={40}
        milestones={MILESTONES}
        caption="Caption"
      />,
    );
    await expectNoA11yViolations(container);
    rerender(<EvidenceMeter label="Trades" value={0} max={40} state="unknown" />);
    await expectNoA11yViolations(container);
  });
});
