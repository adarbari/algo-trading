import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { OutcomeDots, type OutcomeDot } from './OutcomeDots';

const ITEMS: OutcomeDot[] = [
  { label: 'Trend: Passed', tone: 'positive' },
  { label: 'Volume: Near miss', tone: 'warning' },
  { label: 'Spread: Missed', tone: 'negative' },
];

describe('OutcomeDots', () => {
  it('is one image whose name lists every item in order', () => {
    render(<OutcomeDots items={ITEMS} label="Criteria" />);
    expect(screen.getByRole('img')).toHaveAccessibleName(
      'Criteria: Trend: Passed, Volume: Near miss, Spread: Missed',
    );
  });

  it('draws one square per item in the item tone', () => {
    const { container } = render(<OutcomeDots items={ITEMS} label="Criteria" />);
    const dots = [...container.querySelectorAll('[data-tone]')];
    expect(dots.map((d) => d.getAttribute('data-tone'))).toEqual([
      'positive',
      'warning',
      'negative',
    ]);
  });

  it('says so when there are no items', () => {
    render(<OutcomeDots items={[]} label="Criteria" />);
    expect(screen.getByRole('img')).toHaveAccessibleName('Criteria: none');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<OutcomeDots items={ITEMS} label="Criteria" />);
    await expectNoA11yViolations(container);
  });
});
