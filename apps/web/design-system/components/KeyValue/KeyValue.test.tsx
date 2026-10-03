import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { KeyValue } from './KeyValue';

describe('KeyValue', () => {
  it('renders a definition list of terms and formatted values with tones', () => {
    render(
      <KeyValue
        label="Details"
        items={[
          { label: 'Market cap', value: 4_870_000_000_000, format: { kind: 'currency-compact' } },
          { label: 'From high', value: -0.034, format: { kind: 'delta' } },
          { label: 'Yield', value: null, format: { kind: 'percent' } },
        ]}
      />,
    );
    expect(screen.getByText('Market cap').closest('dt')).not.toBeNull();
    expect(screen.getByText('$4.87T').tagName).toBe('DD');
    expect(screen.getByText('−3.40%')).toHaveAttribute('data-tone', 'down');
    expect(screen.getByText('—')).toHaveAttribute('data-tone', 'muted');
  });

  it('shows placeholders while loading and the empty message with no items', () => {
    const { rerender, container } = render(
      <KeyValue loading items={[{ label: 'Close', value: 1 }]} />,
    );
    expect(container.querySelector('dl')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('1')).toBeNull();
    rerender(<KeyValue items={[]} emptyMessage="Nothing selected" />);
    expect(screen.getByText('Nothing selected')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <KeyValue
        items={[
          {
            label: 'Close',
            hint: 'price_stats.close',
            value: 333.69,
            format: { kind: 'currency' },
          },
        ]}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
