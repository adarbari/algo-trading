import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { LinkProvider } from './link-context';
import { TextLink } from './TextLink';

describe('TextLink', () => {
  it('is a plain anchor with its words and icon by default', () => {
    render(
      <TextLink href="/guide" icon="book" keys={['?']}>
        Guide
      </TextLink>,
    );
    const link = screen.getByRole('link', { name: /Guide/ });
    expect(link).toHaveAttribute('href', '/guide');
    expect(link).toHaveTextContent('Guide?');
  });

  it('marks the current page', () => {
    render(
      <TextLink href="/guide" current>
        Guide
      </TextLink>,
    );
    expect(screen.getByRole('link')).toHaveAttribute('aria-current', 'page');
  });

  it('renders an in-app path with the app router link, but not an anchor or a URL', () => {
    render(
      <LinkProvider
        render={({ href, className, children }) => (
          <a href={href} className={className} data-router="yes">
            {children}
          </a>
        )}
      >
        <TextLink href="/guide/fields">In app</TextLink>
        <TextLink href="#reads">Anchor</TextLink>
        <TextLink href="https://example.com">Outside</TextLink>
      </LinkProvider>,
    );
    expect(screen.getByRole('link', { name: 'In app' })).toHaveAttribute('data-router', 'yes');
    expect(screen.getByRole('link', { name: 'Anchor' })).not.toHaveAttribute('data-router');
    expect(screen.getByRole('link', { name: 'Outside' })).not.toHaveAttribute('data-router');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <TextLink href="/guide" icon="book" keys={['?']} current>
        Guide
      </TextLink>,
    );
    await expectNoA11yViolations(container);
  });
});
