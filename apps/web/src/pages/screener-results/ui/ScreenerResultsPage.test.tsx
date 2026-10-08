import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ScreenerResultsPage } from './ScreenerResultsPage';

vi.mock('@/widgets/feature-table', () => ({ ScreenerResults: () => <Text>results</Text> }));
vi.mock('@/widgets/pick-detail', () => ({ PickDetail: () => null }));
vi.mock('@/widgets/price-chart-panel', () => ({ PriceChartPanel: () => null }));

describe('ScreenerResultsPage', () => {
  it('Edit criteria goes straight to the Builder, with no drawer first', async () => {
    const onEdit = vi.fn();
    render(
      <ScreenerResultsPage
        id="my-vrp"
        onEdit={onEdit}
        onOpenTicker={vi.fn()}
        onCompare={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'my-vrp' })).toBeInTheDocument();
    expect(screen.getByText('results')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Edit criteria' }));
    expect(onEdit).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
