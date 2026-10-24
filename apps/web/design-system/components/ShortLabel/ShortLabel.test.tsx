import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ShortLabel } from './ShortLabel';

describe('ShortLabel', () => {
  it('renders both wordings; the short one is decorative', () => {
    render(<ShortLabel short="Data: complete">Data: 22 Oct, complete</ShortLabel>);
    expect(screen.getByText('Data: 22 Oct, complete')).toBeInTheDocument();
    expect(screen.getByText('Data: complete')).toHaveAttribute('aria-hidden', 'true');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <button type="button" aria-label="Data: 22 Oct, complete">
        <ShortLabel short="Data: complete">Data: 22 Oct, complete</ShortLabel>
      </button>,
    );
    await expectNoA11yViolations(container);
  });
});
