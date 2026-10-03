import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Text } from './Text';

describe('Text', () => {
  it('renders a span at the base size by default', () => {
    render(<Text>IV rank</Text>);
    const node = screen.getByText('IV rank');
    expect(node.tagName).toBe('SPAN');
    expect(node).toHaveAttribute('data-size', 'base');
    expect(node).toHaveAttribute('data-tone', 'default');
  });

  it('lets the caller pick the semantic element', () => {
    render(<Text as="p">A paragraph</Text>);
    expect(screen.getByText('A paragraph').tagName).toBe('P');
  });

  it('exposes size, tone, numeric and mono as styling hooks, never as inline style', () => {
    render(
      <Text size="md" tone="up" numeric mono>
        +1.24%
      </Text>,
    );
    const node = screen.getByText('+1.24%');
    expect(node).toHaveAttribute('data-size', 'md');
    expect(node).toHaveAttribute('data-tone', 'up');
    expect(node).toHaveAttribute('data-numeric');
    expect(node).toHaveAttribute('data-mono');
    expect(node).not.toHaveAttribute('style');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Text as="p">Body</Text>
        <Text size="sm" tone="muted">
          Caption
        </Text>
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
