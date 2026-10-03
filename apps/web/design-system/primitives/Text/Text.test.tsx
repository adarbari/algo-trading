import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Text } from './Text';

describe('Text', () => {
  it('renders a semantic element for its variant', () => {
    render(<Text variant="title">Screener</Text>);
    expect(screen.getByRole('heading', { level: 1, name: 'Screener' })).toBeInTheDocument();
  });

  it('lets the caller pick the element', () => {
    render(
      <Text variant="heading" as="h3">
        Legs
      </Text>,
    );
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Legs');
  });

  it('exposes tone, numeric and mono as styling hooks, never as inline style', () => {
    render(
      <Text tone="up" numeric mono>
        +1.24%
      </Text>,
    );
    const node = screen.getByText('+1.24%');
    expect(node).toHaveAttribute('data-tone', 'up');
    expect(node).toHaveAttribute('data-numeric');
    expect(node).toHaveAttribute('data-mono');
    expect(node).not.toHaveAttribute('style');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Text variant="title">Title</Text>
        <Text>Body</Text>
        <Text variant="caption" tone="muted">
          Caption
        </Text>
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
