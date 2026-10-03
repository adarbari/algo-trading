import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Heading } from './Heading';

describe('Heading', () => {
  it('renders the level as an h element sized for it', () => {
    render(<Heading level={1}>Screener</Heading>);
    const node = screen.getByRole('heading', { level: 1, name: 'Screener' });
    expect(node).toHaveAttribute('data-size', '2xl');
  });

  it('panel headings are 13 px unless overridden', () => {
    render(
      <>
        <Heading level={2}>Legs</Heading>
        <Heading level={3} size="lg">
          Greeks
        </Heading>
      </>,
    );
    expect(screen.getByRole('heading', { level: 2 })).toHaveAttribute('data-size', 'base');
    expect(screen.getByRole('heading', { level: 3 })).toHaveAttribute('data-size', 'lg');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Heading level={1}>Page</Heading>
        <Heading level={2}>Panel</Heading>
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
