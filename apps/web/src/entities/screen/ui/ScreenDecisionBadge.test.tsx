import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ScreenDecisionBadge } from './ScreenDecisionBadge';

describe('ScreenDecisionBadge', () => {
  it('says the decision in words', async () => {
    const { container } = render(
      <>
        <ScreenDecisionBadge decision="QUALIFIED" />
        <ScreenDecisionBadge decision="LIQUIDITY_RISK" />
        <ScreenDecisionBadge decision="SKIPPED" />
      </>,
    );
    expect(screen.getByText('Qualified')).toBeInTheDocument();
    expect(screen.getByText('Liquidity risk')).toBeInTheDocument();
    expect(screen.getByText('Skipped')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
