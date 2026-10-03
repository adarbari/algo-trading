import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Surface } from './Surface';

describe('Surface', () => {
  it('is a bordered panel surface by default', () => {
    render(<Surface aria-label="panel">x</Surface>);
    const node = screen.getByLabelText('panel');
    expect(node).toHaveAttribute('data-tone', 'surface');
    expect(node).toHaveAttribute('data-border', 'all');
    expect(node).toHaveAttribute('data-radius', 'lg');
    expect(node).not.toHaveAttribute('style');
  });

  it('renders a labelled section', () => {
    render(
      <Surface as="section" aria-label="Drill-down" borderTone="accent">
        x
      </Surface>,
    );
    expect(screen.getByRole('region', { name: 'Drill-down' })).toHaveAttribute(
      'data-border-tone',
      'accent',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Surface as="section" aria-label="Summary" padding={4}>
        content
      </Surface>,
    );
    await expectNoA11yViolations(container);
  });
});
