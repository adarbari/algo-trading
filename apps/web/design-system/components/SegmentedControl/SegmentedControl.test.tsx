import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { SegmentedControl } from './SegmentedControl';

const OPTIONS = [
  { value: '3M', label: '3M' },
  { value: '1Y', label: '1Y' },
  { value: '2Y', label: '2Y' },
];

describe('SegmentedControl', () => {
  it('is a named radio group with the default selected', () => {
    render(<SegmentedControl aria-label="Range" options={OPTIONS} defaultValue="1Y" />);
    expect(screen.getByRole('radiogroup', { name: 'Range' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '1Y' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: '3M' })).toHaveAttribute('tabindex', '-1');
  });

  it('selects on click and reports the value', async () => {
    const onValueChange = vi.fn();
    render(<SegmentedControl aria-label="Range" options={OPTIONS} onValueChange={onValueChange} />);
    await userEvent.click(screen.getByRole('radio', { name: '2Y' }));
    expect(onValueChange).toHaveBeenCalledWith('2Y');
    expect(screen.getByRole('radio', { name: '2Y' })).toHaveAttribute('aria-checked', 'true');
  });

  it('moves and selects with arrow keys, wrapping, and Home / End', async () => {
    const onValueChange = vi.fn();
    render(
      <SegmentedControl
        aria-label="Range"
        options={OPTIONS}
        defaultValue="3M"
        onValueChange={onValueChange}
      />,
    );
    await userEvent.tab();
    expect(screen.getByRole('radio', { name: '3M' })).toHaveFocus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: '1Y' })).toHaveFocus();
    await userEvent.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(screen.getByRole('radio', { name: '2Y' })).toHaveAttribute('aria-checked', 'true');
    await userEvent.keyboard('{Home}');
    expect(onValueChange).toHaveBeenLastCalledWith('3M');
  });

  it('follows a controlled value', () => {
    const { rerender } = render(
      <SegmentedControl aria-label="Range" options={OPTIONS} value="3M" />,
    );
    rerender(<SegmentedControl aria-label="Range" options={OPTIONS} value="2Y" />);
    expect(screen.getByRole('radio', { name: '2Y' })).toHaveAttribute('aria-checked', 'true');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <SegmentedControl aria-label="Range" options={OPTIONS} size="sm" />,
    );
    await expectNoA11yViolations(container);
  });
});
