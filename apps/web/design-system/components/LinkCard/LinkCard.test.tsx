import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { LinkCard } from './LinkCard';

describe('LinkCard', () => {
  it('names the link by its title and shows kicker, text, example and footer', () => {
    render(
      <LinkCard
        href="/guide/edges/x"
        kicker="Who?"
        title="Slow to update"
        description="Text."
        exampleLabel="e.g."
        example="drift"
        footer={<span>3 edges</span>}
      />,
    );
    expect(screen.getByRole('link', { name: 'Slow to update' })).toHaveAttribute(
      'href',
      '/guide/edges/x',
    );
    expect(screen.getByRole('heading', { level: 3 })).toBeInTheDocument();
    expect(screen.getByText('Who?')).toBeInTheDocument();
    expect(screen.getByText('Text.')).toBeInTheDocument();
    expect(screen.getByText('e.g. drift')).toBeInTheDocument();
    expect(screen.getByText('3 edges')).toBeInTheDocument();
  });

  it('renders only the title when nothing else is given', () => {
    render(<LinkCard href="/a" title="Only" headingLevel={2} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Only' })).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<LinkCard href="/a" title="T" kicker="K" description="D" />);
    await expectNoA11yViolations(container);
  });
});
