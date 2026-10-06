import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ScreenerBuilderPage } from './ScreenerBuilderPage';

const probe = vi.hoisted(() => ({ id: '' }));

vi.mock('@/features/screener-builder', () => ({
  ScreenerBuilderProvider: ({ id, children }: { id: string; children: React.ReactNode }) => {
    probe.id = id;
    return <>{children}</>;
  },
}));
vi.mock('@/widgets/draft-bar', () => ({ DraftBar: () => <Text>draft bar</Text> }));
vi.mock('@/widgets/describe-screen', () => ({ DescribeScreen: () => <Text>describe</Text> }));
vi.mock('@/widgets/criteria-table', () => ({ CriteriaTable: () => <Text>criteria</Text> }));
vi.mock('@/widgets/screen-summary', () => ({ ScreenSummary: () => <Text>summary</Text> }));
vi.mock('@/widgets/screen-funnel', () => ({ ScreenFunnel: () => <Text>funnel</Text> }));
vi.mock('@/widgets/feature-table', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    PreviewResults: ({ onOpen }: { onOpen: (symbol: string) => void }) => (
      <Button
        onClick={() => {
          onOpen('AAPL');
        }}
      >
        open ticker
      </Button>
    ),
  };
});

describe('ScreenerBuilderPage', () => {
  it('lays the Builder out around one provider and passes navigation through', async () => {
    const onOpenTicker = vi.fn();
    render(<ScreenerBuilderPage id="my-vrp" onOpenTicker={onOpenTicker} onDeleted={vi.fn()} />);
    expect(probe.id).toBe('my-vrp');
    for (const text of ['draft bar', 'describe', 'criteria', 'summary', 'funnel'])
      expect(screen.getByText(text)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'open ticker' }));
    expect(onOpenTicker).toHaveBeenCalledWith('AAPL');
  });
});
