import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { edgeFixture } from '@/entities/edge';

import { SetupRules } from './SetupRules';

vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

describe('SetupRules', () => {
  it('states the rules as a grid with the historical exit rule, screens linked', () => {
    render(<SetupRules edge={edgeFixture('momentum_12_1')} />);
    expect(screen.getByRole('heading', { level: 2, name: 'The rules' })).toBeInTheDocument();
    for (const label of ['Idea', 'Screens', 'Picks', 'Historical exit rule']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'momentum_12_1' })).toHaveAttribute(
      'href',
      '/screeners/momentum_12_1',
    );
    expect(screen.getByText('help edge_definition')).toBeInTheDocument();
  });

  it('keeps the comparison, the test and the sources behind a disclosure, linked only with a url', async () => {
    render(<SetupRules edge={edgeFixture('momentum_12_1')} />);
    expect(screen.getByText('Compared against')).not.toBeVisible();
    await userEvent.click(screen.getByText('Compared against, tested, and why it should last'));
    expect(screen.getByText('Compared against')).toBeVisible();
    expect(screen.getByText('Test')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Jegadeesh and Titman 1993/ })).toHaveAttribute(
      'href',
      'https://example.org/jt1993',
    );
    expect(screen.getByText('Daniel and Moskowitz 2016')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Daniel/ })).not.toBeInTheDocument();
    expect(screen.getByText('help edge_persistence')).toBeInTheDocument();
  });
});
