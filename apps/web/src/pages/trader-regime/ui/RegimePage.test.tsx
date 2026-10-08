import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { RegimePage } from './RegimePage';

vi.mock('@/widgets/regime-header', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeHeader: () => <Text>header widget</Text> };
});
vi.mock('@/widgets/regime-legend', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeLegend: () => <Text>legend widget</Text> };
});
vi.mock('@/widgets/regime-cycles', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeCycles: () => <Text>cycles widget</Text> };
});
vi.mock('@/widgets/regime-episodes', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeEpisodes: () => <Text>episodes widget</Text> };
});
vi.mock('@/widgets/regime-indicators', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeIndicators: () => <Text>indicators widget</Text> };
});
vi.mock('@/widgets/regime-sizing', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeSizing: () => <Text>sizing widget</Text> };
});

describe('RegimePage', () => {
  it('composes the header, legend, cycles, warning signs, sizing, episodes under one heading', async () => {
    const { container } = render(<RegimePage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Regime' })).toBeVisible();
    const order = [
      'header widget',
      'legend widget',
      'cycles widget',
      'indicators widget',
      'sizing widget',
      'episodes widget',
    ];
    const nodes = order.map((text) => screen.getByText(text));
    nodes.forEach((node) => {
      expect(node).toBeVisible();
    });
    nodes.slice(1).forEach((node, i) => {
      const previous = nodes[i] as HTMLElement;
      expect(
        previous.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });
    await expectNoA11yViolations(container);
  });
});
