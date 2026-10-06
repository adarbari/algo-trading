import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { RegimePage } from './RegimePage';

vi.mock('@/widgets/regime-header', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeHeader: () => <Text>header widget</Text> };
});
vi.mock('@/widgets/regime-indicators', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeIndicators: () => <Text>indicators widget</Text> };
});
vi.mock('@/widgets/regime-sizing', async () => {
  const { Text } = await import('@algotrade/ui');
  return { RegimeSizing: () => <Text>sizing widget</Text> };
});
vi.mock('@/widgets/reading-list', async () => {
  const { Text } = await import('@algotrade/ui');
  return { ReadingList: () => <Text>reading list widget</Text> };
});

describe('RegimePage', () => {
  it('composes the header, the warning signs, the sizing rules and the reading list under one heading', async () => {
    const { container } = render(<RegimePage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Regime' })).toBeVisible();
    expect(screen.getByText('header widget')).toBeVisible();
    expect(screen.getByText('indicators widget')).toBeVisible();
    expect(screen.getByText('sizing widget')).toBeVisible();
    expect(screen.getByText('reading list widget')).toBeVisible();
    await expectNoA11yViolations(container);
  });
});
