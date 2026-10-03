import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Divider } from './Divider';

describe('Divider', () => {
  it('is a horizontal separator by default', () => {
    render(<Divider />);
    expect(screen.getByRole('separator')).toHaveAttribute('data-orientation', 'horizontal');
  });

  it('can be vertical', () => {
    render(<Divider orientation="vertical" />);
    expect(screen.getByRole('separator')).toHaveAttribute('aria-orientation', 'vertical');
  });

  it('can be hidden from assistive technology', () => {
    render(<Divider decorative />);
    expect(screen.queryByRole('separator')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Divider />
        <Divider orientation="vertical" tone="soft" />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
