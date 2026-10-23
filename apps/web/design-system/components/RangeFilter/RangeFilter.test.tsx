import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { RangeFilter } from './RangeFilter';

const BINS = [
  { start: 0, end: 7, count: 12 },
  { start: 7, end: 14, count: 30 },
  { start: 14, end: 21, count: 5 },
];

describe('RangeFilter', () => {
  it('reports a minimum and clearing one end drops the key', async () => {
    const onChange = vi.fn();
    render(<RangeFilter value={{ max: 14 }} onChange={onChange} label="DTE" />);
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Min' }), '3{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({ min: 3, max: 14 });
    const max = screen.getByRole('spinbutton', { name: 'Max' });
    await userEvent.clear(max);
    await userEvent.keyboard('{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({});
  });

  it('draws the histogram hidden from assistive tech and gives its counts as text', () => {
    const { container } = render(
      <RangeFilter value={{}} onChange={vi.fn()} label="DTE" bins={BINS} />,
    );
    expect(container.querySelector('[aria-hidden="true"] svg')).not.toBeNull();
    expect(screen.getByText(/47 values/)).toBeInTheDocument();
  });

  it('says how many rows are unknown, only when there are some', () => {
    const { rerender } = render(
      <RangeFilter value={{}} onChange={vi.fn()} label="DTE" unknownCount={12} />,
    );
    expect(screen.getByText('Unknown: 12')).toBeInTheDocument();
    rerender(<RangeFilter value={{}} onChange={vi.fn()} label="DTE" unknownCount={0} />);
    expect(screen.queryByText(/Unknown/)).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <RangeFilter
        value={{ min: 3 }}
        onChange={vi.fn()}
        label="DTE"
        unit="days"
        bins={BINS}
        unknownCount={4}
      />,
    );
    await expectNoA11yViolations(container);
  });

  it('swaps reversed ends and clamps to the bounds', async () => {
    const onChange = vi.fn();
    render(
      <RangeFilter
        value={{ max: 10 }}
        onChange={onChange}
        label="DTE"
        bounds={{ min: 0, max: 30 }}
        unknownCount={2}
        unknownHelp={<button type="button">Help</button>}
      />,
    );
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Min' }), '20{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({ min: 10, max: 20 });
    expect(screen.getByRole('button', { name: 'Help' })).toBeInTheDocument();
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Max' }), '99{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({ max: 30 });
  });
});
