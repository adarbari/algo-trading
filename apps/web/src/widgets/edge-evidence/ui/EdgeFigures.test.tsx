import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { edgeFixture } from '@/entities/edge';
import { expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import { EdgeFigures } from './EdgeFigures';

vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

stubElementSize();

const verdict = edgeFixture('momentum_12_1').verdict;

describe('EdgeFigures', () => {
  it('shows the sides of the split side by side with the out-of-sample column marked and n= when thin', async () => {
    const { container } = render(<EdgeFigures verdict={verdict} />);
    const table = screen.getByRole('grid', { name: 'In-sample, out-of-sample and all figures' });
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(headers).toEqual(['Figure', 'In-sample', 'Out-of-sample · n=6', 'All']);
    expect(
      within(table)
        .getAllByRole('columnheader')
        .find((h) => h.textContent.startsWith('Out-of-sample')),
    ).toHaveAttribute('data-emphasis', 'true');
    const win = within(table).getByRole('row', { name: /Win rate/ });
    expect(win).toHaveTextContent('56.0%');
    expect(win).toHaveTextContent('57.0%');
    expect(within(table).getByRole('row', { name: /^Lift/ })).toHaveTextContent('+5.0 pts');
    expect(screen.getByText('help win_rate')).toBeInTheDocument();
    expect(screen.getByText('help overfitting_probability')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('reads a figure the run did not store as missing, never zero', () => {
    render(<EdgeFigures verdict={verdict} />);
    const pbo = screen.getByRole('row', { name: /Chance of overfitting/ });
    expect(pbo).toHaveTextContent('—');
    expect(pbo).not.toHaveTextContent('0.00');
  });

  it('says there are no figures without an official result', () => {
    render(<EdgeFigures verdict={{ ...verdict, columns: [] }} />);
    expect(screen.getByText('No figures yet: the edge has no official result')).toBeInTheDocument();
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  });
});
