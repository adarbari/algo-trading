import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { PartList } from './PartList';

describe('PartList', () => {
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
