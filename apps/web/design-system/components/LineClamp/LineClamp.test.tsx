import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { LineClamp } from './LineClamp';

describe('LineClamp', () => {
  it('keeps the whole text in the DOM and offers it as the tooltip', () => {
    render(<LineClamp title="the whole text">the whole text</LineClamp>);
    expect(screen.getByTitle('the whole text')).toHaveTextContent('the whole text');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<LineClamp>text</LineClamp>);
    await expectNoA11yViolations(container);
  });
});
