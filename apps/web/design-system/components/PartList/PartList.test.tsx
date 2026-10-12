import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { PartList } from './PartList';

describe('PartList', () => {
  it('keeps the callers keys, so a reorder keeps each card mounted', () => {
    const { rerender } = render(
      <PartList aria-label="Parts">
        <p key="a">first</p>
        <p key="b">second</p>
      </PartList>,
    );
    const first = screen.getByText('first');
    rerender(
      <PartList aria-label="Parts">
        <p key="b">second</p>
        <p key="a">first</p>
      </PartList>,
    );
    expect(screen.getByText('first')).toBe(first);
  });

  it('is a named ordered list with one item per card', async () => {
    const { container } = render(
      <PartList aria-label="Parts">
        <p>first</p>
        <p>second</p>
      </PartList>,
    );
    expect(screen.getByRole('list', { name: 'Parts' }).tagName).toBe('OL');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    await expectNoA11yViolations(container);
  });
});
