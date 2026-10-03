import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Mono } from './Mono';

describe('Mono', () => {
  it('renders a span for symbols', () => {
    render(<Mono>SPY</Mono>);
    expect(screen.getByText('SPY').tagName).toBe('SPAN');
  });

  it('renders code when asked', () => {
    render(<Mono code>min_iv_rank</Mono>);
    expect(screen.getByText('min_iv_rank').tagName).toBe('CODE');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Mono tone="muted">EQ:BBG000BDTBL9</Mono>);
    await expectNoA11yViolations(container);
  });
});
