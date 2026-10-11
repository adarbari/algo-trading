import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { edgeFixture } from '@/entities/edge';

import { EdgeDefinition } from './EdgeDefinition';

vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

describe('EdgeDefinition', () => {
  it('defines the edge in six parts, with screens linked and sources linked only with a url', () => {
    render(<EdgeDefinition edge={edgeFixture('momentum_12_1')} />);
    for (const label of ['1 · Idea', '2 · Screens', '3 · Picks', '4 · Trade', '6 · Test']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'momentum_12_1' })).toHaveAttribute(
      'href',
      '/screeners/momentum_12_1',
    );
    expect(screen.getByRole('link', { name: /Jegadeesh and Titman 1993/ })).toHaveAttribute(
      'href',
      'https://example.org/jt1993',
    );
    expect(screen.getByText('Daniel and Moskowitz 2016')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Daniel/ })).not.toBeInTheDocument();
    for (const id of ['edge_definition', 'edge_persistence']) {
      expect(screen.getByText(`help ${id}`)).toBeInTheDocument();
    }
  });
});
