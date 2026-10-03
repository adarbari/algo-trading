import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { VisuallyHidden } from './VisuallyHidden';

describe('VisuallyHidden', () => {
  it('keeps the text in the accessibility tree', () => {
    render(
      <button type="button">
        <VisuallyHidden>Close</VisuallyHidden>
      </button>,
    );
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<VisuallyHidden as="div">Caption</VisuallyHidden>);
    await expectNoA11yViolations(container);
  });
});
