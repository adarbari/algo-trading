import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { regimeFixture, unknownRegimeFixture } from '../model/fixtures';

import { RegimeHeadline } from './RegimeHeadline';

describe('RegimeHeadline', () => {
  it('shows the weather word, the sentence and the three scores', async () => {
    const { container } = render(<RegimeHeadline regime={regimeFixture()} />);
    expect(screen.getByRole('heading', { level: 3, name: 'Clouds building' })).toBeVisible();
    expect(screen.getByText('1 of 3 warning signs is on. The fast signs are quiet.')).toBeVisible();
    expect(screen.getByRole('meter', { name: 'Slow-warning score' })).toHaveAttribute(
      'aria-valuenow',
      '62',
    );
    expect(screen.getByRole('meter', { name: 'Market stress score' })).toHaveAttribute(
      'aria-valuenow',
      '18',
    );
    expect(screen.getByRole('meter', { name: 'Fragility' })).toHaveAttribute('aria-valuenow', '40');
    await expectNoA11yViolations(container);
  });

  it('shows why each score and the regime are unknown instead of a number', () => {
    render(<RegimeHeadline regime={unknownRegimeFixture()} />);
    expect(screen.getByRole('heading', { level: 3, name: 'Not computed' })).toBeVisible();
    expect(screen.getByText('The regime is not in the catalogue yet.')).toBeVisible();
    expect(
      screen.getByRole('img', { name: /Slow-warning score: unknown. regime not built/ }),
    ).toBeVisible();
    expect(screen.queryByRole('meter')).toBeNull();
  });
});
