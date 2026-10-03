import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { NavTabs, type NavLinkRenderProps } from './NavTabs';

const ITEMS = [
  { href: '/ideas', label: 'Ideas' },
  { href: '/explore', label: 'Explore' },
];

describe('NavTabs', () => {
  it('is a named navigation landmark marking the current page', () => {
    render(<NavTabs items={ITEMS} activeHref="/explore" aria-label="Trader sections" />);
    expect(screen.getByRole('navigation', { name: 'Trader sections' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Explore' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Ideas' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: 'Ideas' })).toHaveAttribute('href', '/ideas');
  });

  it("renders the app's link component through renderLink", () => {
    const seen: string[] = [];
    const RouterLink = ({ href, children, ...rest }: NavLinkRenderProps) => {
      seen.push(href);
      return (
        <a {...rest} href={`#${href}`} data-router="">
          {children}
        </a>
      );
    };
    render(
      <NavTabs
        items={ITEMS}
        activeHref="/ideas"
        aria-label="Sections"
        renderLink={(link) => <RouterLink {...link} />}
      />,
    );
    expect(seen).toEqual(['/ideas', '/explore']);
    expect(screen.getByRole('link', { name: 'Ideas' })).toHaveAttribute('data-router');
    expect(screen.getByRole('link', { name: 'Ideas' })).toHaveAttribute('aria-current', 'page');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <NavTabs items={ITEMS} activeHref="/ideas" aria-label="Sections" />,
    );
    await expectNoA11yViolations(container);
  });
});
