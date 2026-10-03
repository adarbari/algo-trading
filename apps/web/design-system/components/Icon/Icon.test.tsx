import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Icon, ICON_NAMES } from './Icon';

describe('Icon', () => {
  it('is decorative (hidden from assistive technology) without a label', () => {
    const { container } = render(<Icon name="close" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('data-size', 'md');
    expect(svg).not.toHaveAttribute('role');
  });

  it('is an image with a name when labelled', () => {
    render(<Icon name="alert" label="Failed" tone="negative" />);
    expect(screen.getByRole('img', { name: 'Failed' })).toHaveAttribute('data-tone', 'negative');
  });

  it('draws every icon in the set with currentColor strokes', () => {
    for (const name of ICON_NAMES) {
      const { container, unmount } = render(<Icon name={name} />);
      const svg = container.querySelector('svg');
      expect(svg?.getAttribute('stroke')).toBe('currentColor');
      expect(svg?.childNodes.length).toBeGreaterThan(0);
      unmount();
    }
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Icon name="search" />
        <Icon name="spinner" spin label="Loading" />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
