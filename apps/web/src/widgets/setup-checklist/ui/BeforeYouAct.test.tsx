import { Text } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { BeforeYouAct } from './BeforeYouAct';

vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
}));

describe('BeforeYouAct', () => {
  it('lists the checks that hold for any setup, with the section help', async () => {
    const { container } = render(<BeforeYouAct />);
    expect(screen.getByRole('heading', { level: 2, name: 'Before you act' })).toBeInTheDocument();
    expect(screen.getByText('help setup_before_you_act')).toBeInTheDocument();
    const list = screen.getByRole('list', { name: 'Before you act' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);
    expect(within(list).getByText(/Backtests are hypothetical/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
