import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { DecisionBadge } from './DecisionBadge';

describe('DecisionBadge', () => {
  it('says the decision in words', async () => {
    const { container } = render(
      <>
        <DecisionBadge decision="QUALIFIED" />
        <DecisionBadge decision="LIQUIDITY_RISK" />
        <DecisionBadge decision="SKIPPED" />
      </>,
    );
    expect(screen.getByText('Qualified')).toBeInTheDocument();
    expect(screen.getByText('Liquidity risk')).toBeInTheDocument();
    expect(screen.getByText('Skipped')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
