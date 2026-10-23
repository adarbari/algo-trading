import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ZeroResults } from './ZeroResults';

const ITEMS = [
  { id: 'liq', label: 'Switch off Liquidity', gives: 1310 },
  { id: 'dte', label: 'Switch off DTE', gives: 4 },
];

describe('ZeroResults', () => {
  it('lists the recovery chips with their counts and reports the pick', async () => {
    const onPick = vi.fn();
    const { container } = render(
      <ZeroResults
        title="No ideas match all 3 filters"
        items={ITEMS}
        onPick={onPick}
        onClearAll={vi.fn()}
      />,
    );
    expect(screen.getByText('No ideas match all 3 filters')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Switch off Liquidity gives 1,310' }));
    expect(onPick).toHaveBeenCalledWith('liq');
    await expectNoA11yViolations(container);
  });

  it('clears all filters', async () => {
    const onClearAll = vi.fn();
    render(<ZeroResults title="None" items={[]} onPick={vi.fn()} onClearAll={onClearAll} />);
    await userEvent.click(screen.getByRole('button', { name: 'Clear all' }));
    expect(onClearAll).toHaveBeenCalledOnce();
  });
});
