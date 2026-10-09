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
vi.mock('@/widgets/regime-timing', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeTiming: () => <Text>timing widget</Text> };
});

describe('RegimePage', () => {
  it('composes Now, Why and History under one heading and a section nav', async () => {
    const { container } = render(<RegimePage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Regime' })).toBeVisible();
    const nav = screen.getByRole('navigation', { name: 'Regime sections' });
    expect(nav.querySelectorAll('a')).toHaveLength(3);
    const order = [
      'header widget',
      'sizing widget',
      'indicators widget',
      'legend widget',
      'cycles widget',
      'episodes widget',
      'timing widget',
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
    expect(screen.getByRole('region', { name: 'Now' })).toContainElement(nodes[0] as HTMLElement);
    expect(screen.getByRole('region', { name: 'Why' })).toContainElement(nodes[2] as HTMLElement);
    expect(screen.getByRole('region', { name: 'History' })).toContainElement(
      nodes[6] as HTMLElement,
    );
    await expectNoA11yViolations(container);
  });
});
