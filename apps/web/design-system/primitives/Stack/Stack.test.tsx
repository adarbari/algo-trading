import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Stack } from './Stack';

describe('Stack', () => {
  it('renders a column with the default gap', () => {
    render(<Stack aria-label="list">child</Stack>);
    const node = screen.getByLabelText('list');
    expect(node).toHaveAttribute('data-direction', 'column');
    expect(node).toHaveAttribute('data-gap', '2');
  });

  it('renders the semantic element it is given', () => {
    render(
      <Stack as="nav" aria-label="Primary" direction="row">
        links
      </Stack>,
    );
    expect(screen.getByRole('navigation', { name: 'Primary' })).toHaveAttribute(
      'data-direction',
      'row',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Stack as="main" aria-label="Content" gap={4} padding={4}>
        content
      </Stack>,
    );
    await expectNoA11yViolations(container);
  });
});
