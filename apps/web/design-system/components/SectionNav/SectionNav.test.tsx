import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Box } from '../../primitives/Box';
import { expectNoA11yViolations } from '../../testing';
import { SectionNav } from './SectionNav';

const ITEMS = [
  { id: 'now', label: 'Now' },
  { id: 'why', label: 'Why' },
];

function Page() {
  return (
    <div>
      <SectionNav items={ITEMS} aria-label="Page sections" />
      <Box as="section" id="now">
        now
      </Box>
      <Box as="section" id="why">
        why
      </Box>
    </div>
  );
}

describe('SectionNav', () => {
  it('is a named landmark linking each section, the first marked', () => {
    render(<Page />);
    expect(screen.getByRole('navigation', { name: 'Page sections' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Now' })).toHaveAttribute('href', '#now');
    expect(screen.getByRole('link', { name: 'Now' })).toHaveAttribute('aria-current', 'location');
    expect(screen.getByRole('link', { name: 'Why' })).not.toHaveAttribute('aria-current');
  });

  it('marks the section just chosen', async () => {
    render(<Page />);
    await userEvent.setup().click(screen.getByRole('link', { name: 'Why' }));
    expect(screen.getByRole('link', { name: 'Why' })).toHaveAttribute('aria-current', 'location');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Page />);
    await expectNoA11yViolations(container);
  });
});
