import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { NavList } from './NavList';

const ITEMS = [
  { href: '/guide', label: 'Start here' },
  {
    href: '/guide/fields',
    label: 'Fields',
    count: 1234,
    children: [
      { href: '/guide/fields/rel_volume', label: 'rel_volume', mono: true, current: true },
    ],
  },
];

describe('NavList', () => {
  it('is a named navigation landmark of nested lists with counts', () => {
    render(<NavList aria-label="Guide" items={ITEMS} />);
    const nav = screen.getByRole('navigation', { name: 'Guide' });
    expect(within(nav).getAllByRole('list')).toHaveLength(2);
    expect(within(nav).getByRole('link', { name: /Fields/ })).toHaveTextContent('Fields1,234');
  });

  it('marks the current row', () => {
    render(<NavList aria-label="Guide" items={ITEMS} />);
    expect(screen.getByRole('link', { name: 'rel_volume' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<NavList aria-label="Guide" items={ITEMS} />);
    await expectNoA11yViolations(container);
  });
});
