import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { BarList } from './BarList';

const items = [
  { id: 'u', label: 'Universe', value: 4203 },
  { id: 'iv', label: 'IV30 ≥ 50%', value: 486 },
  { id: 'none', label: 'Nothing left', value: 0 },
];

describe('BarList', () => {
  it('renders a named list whose rows read as label and value', () => {
    render(<BarList label="Funnel" items={items} />);
    const rows = within(screen.getByRole('list', { name: 'Funnel' })).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Universe4,203');
    expect(rows[1]).toHaveTextContent('IV30 ≥ 50%486');
  });

  it('scales bars to max, with a sliver for small non-zero values and none for zero', () => {
    const { container } = render(<BarList label="Funnel" items={items} max={100000} />);
    const fills = container.querySelectorAll<HTMLElement>('[data-tone]');
    expect(fills[0]?.style.getPropertyValue('--share')).toBe('4.203%');
    expect(fills[1]?.style.getPropertyValue('--share')).toBe('1%');
    expect(fills[2]?.style.getPropertyValue('--share')).toBe('0%');
  });

  it('uses display text when given', () => {
    render(
      <BarList
        label="Tiers"
        max={1}
        items={[{ id: 'a', label: 'S&P 500', value: 0.996, display: '99.6%' }]}
      />,
    );
    expect(screen.getByText('99.6%')).toBeInTheDocument();
  });

  it('shows empty, loading and error states', () => {
    const { rerender } = render(<BarList label="F" items={[]} emptyMessage="No criteria" />);
    expect(screen.getByText('No criteria')).toBeInTheDocument();
    rerender(<BarList label="F" items={items} loading />);
    expect(screen.getByRole('list')).toHaveAttribute('aria-busy', 'true');
    rerender(<BarList label="F" items={items} error="Failed" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Failed');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<BarList label="Funnel" layout="stacked" items={items} />);
    await expectNoA11yViolations(container);
  });
});
