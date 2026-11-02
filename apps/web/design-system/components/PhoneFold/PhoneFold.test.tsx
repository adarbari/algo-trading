import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { PhoneFold } from './PhoneFold';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('PhoneFold', () => {
  it('wide: shows the content in place, with no summary', async () => {
    vi.stubGlobal('innerWidth', 1400);
    const { container } = render(<PhoneFold label="Record">58% win rate</PhoneFold>);
    expect(screen.getByText('58% win rate')).toBeVisible();
    expect(screen.queryByRole('button', { name: /Record/ })).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('narrow: folds the content behind its summary button', async () => {
    vi.stubGlobal('innerWidth', 375);
    const { container } = render(<PhoneFold label="Record">58% win rate</PhoneFold>);
    expect(screen.getByRole('button', { name: /Record/ })).toHaveAttribute('aria-expanded', 'false');
    await expectNoA11yViolations(container);
  });
});
