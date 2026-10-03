import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Checkbox } from './Checkbox';

describe('Checkbox', () => {
  it('toggles by click on its label and by Space', async () => {
    const onCheckedChange = vi.fn();
    render(<Checkbox label="Include ETFs" onCheckedChange={onCheckedChange} />);
    await userEvent.click(screen.getByText('Include ETFs'));
    const box = screen.getByRole('checkbox', { name: 'Include ETFs' });
    expect(box).toBeChecked();
    await userEvent.keyboard(' ');
    expect(box).not.toBeChecked();
    expect(onCheckedChange).toHaveBeenNthCalledWith(1, true, expect.anything());
    expect(onCheckedChange).toHaveBeenNthCalledWith(2, false, expect.anything());
  });

  it('announces the description separately from the name', () => {
    render(<Checkbox label="IV30" description="Our 30-day implied volatility" />);
    const box = screen.getByRole('checkbox', { name: 'IV30' });
    expect(box).toHaveAccessibleDescription('Our 30-day implied volatility');
  });

  it('can leave the tab order (a row box inside a keyboard grid)', () => {
    render(<Checkbox label="Select AAPL" hideLabel excludeFromTabOrder />);
    expect(screen.getByRole('checkbox')).toHaveAttribute('tabindex', '-1');
  });

  it('shows the mixed state', () => {
    render(<Checkbox label="All" indeterminate />);
    const box = screen.getByRole<HTMLInputElement>('checkbox', { name: 'All' });
    expect(box.indeterminate).toBe(true);
    expect(box).toHaveAttribute('aria-checked', 'mixed');
  });

  it('keeps a hidden label accessible', () => {
    render(<Checkbox label="Select AAPL" hideLabel />);
    expect(screen.getByRole('checkbox', { name: 'Select AAPL' })).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Checkbox label="One" description="More detail" />
        <Checkbox label="Two" hideLabel defaultChecked />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
