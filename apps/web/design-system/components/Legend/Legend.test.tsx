import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Legend } from './Legend';

describe('Legend', () => {
  it('renders a labelled list with one item per entry, values as text', () => {
    render(
      <Legend
        label="Option chains"
        items={[
          { label: 'OK', tone: 'positive', value: '3,624' },
          { label: 'Stale', tone: 'warning', value: '515' },
        ]}
      />,
    );
    const list = screen.getByRole('list', { name: 'Option chains' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('OK3,624');
  });

  it('marks swatches decorative and exposes tone and shape as data attributes', () => {
    const { container } = render(
      <Legend swatch="cell" items={[{ label: 'failed', tone: 'negative' }]} />,
    );
    const swatch = container.querySelector('[data-tone]');
    expect(swatch).toHaveAttribute('aria-hidden', 'true');
    expect(swatch).toHaveAttribute('data-tone', 'negative');
    expect(swatch).toHaveAttribute('data-swatch', 'cell');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Legend
        items={[
          { label: 'AAPL', tone: 's1' },
          { label: 'MSFT', tone: 's2' },
        ]}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
