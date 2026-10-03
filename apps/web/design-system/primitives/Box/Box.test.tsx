import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Box } from './Box';

describe('Box', () => {
  it('renders a div with token padding hooks', () => {
    render(
      <Box aria-label="cell" padding={2} paddingX={4}>
        x
      </Box>,
    );
    const node = screen.getByLabelText('cell');
    expect(node.tagName).toBe('DIV');
    expect(node).toHaveAttribute('data-padding', '2');
    expect(node).toHaveAttribute('data-padding-x', '4');
    expect(node).not.toHaveAttribute('style');
  });

  it('renders landmarks', () => {
    render(
      <Box as="main" width="page">
        page
      </Box>,
    );
    expect(screen.getByRole('main')).toHaveAttribute('data-width', 'page');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Box as="section" aria-label="Summary" padding={4}>
        content
      </Box>,
    );
    await expectNoA11yViolations(container);
  });
});
