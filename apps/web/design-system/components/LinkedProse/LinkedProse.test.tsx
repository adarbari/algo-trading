import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { LinkProvider } from '../TextLink';
import { LinkedProse, type LinkedProsePart } from './LinkedProse';

const PARTS: LinkedProsePart[] = [
  { text: 'Check ' },
  { text: 'rel_volume', href: '/guide/fields/rel_volume' },
  { text: ' first.' },
];

describe('LinkedProse', () => {
  it('renders a part with an href as a link and the rest as text, in order', () => {
    const { container } = render(<LinkedProse parts={PARTS} monoLinks />);
    const link = screen.getByRole('link', { name: 'rel_volume' });
    expect(link).toHaveAttribute('href', '/guide/fields/rel_volume');
    expect(container.textContent).toBe('Check rel_volume first.');
  });

  it('opens an in-app path with the app router link', () => {
    render(
      <LinkProvider
        render={({ href, className, children }) => (
          <a href={href} className={className} data-router="yes">
            {children}
          </a>
        )}
      >
        <LinkedProse parts={PARTS} />
      </LinkProvider>,
    );
    expect(screen.getByRole('link')).toHaveAttribute('data-router', 'yes');
  });

  it('renders plain parts without links, in the chosen tone and size', () => {
    render(<LinkedProse parts={[{ text: 'Plain' }]} tone="muted" size="sm" />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Plain')).toHaveAttribute('data-tone', 'muted');
    expect(screen.getByText('Plain')).toHaveAttribute('data-size', 'sm');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<LinkedProse parts={PARTS} monoLinks />);
    await expectNoA11yViolations(container);
  });
});
