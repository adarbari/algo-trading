import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TestResultPage } from './TestResultPage';

vi.mock('@/widgets/feature-table', () => ({ ScreenerResults: () => <Text>results</Text> }));
vi.mock('@/widgets/screener-edge-line', () => ({
  ScreenerEdgeLine: ({ screenerId }: { screenerId: string }) => (
    <Text>{`edge line of ${screenerId}`}</Text>
  ),
}));
vi.mock('@/widgets/pick-detail', () => ({ PickDetail: () => null }));
vi.mock('@/widgets/price-chart-panel', () => ({ PriceChartPanel: () => null }));

const hooks = vi.hoisted(() => ({ runs: vi.fn(), mine: vi.fn() }));
vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerRuns: hooks.runs,
  useMyScreeners: hooks.mine,
}));

const renderPage = (onEdit = vi.fn(), onBuildSetup = vi.fn()) =>
  render(
    <TestResultPage
      id="my-vrp"
      f={undefined}
      onFilterChange={vi.fn()}
      onEdit={onEdit}
      onBuildSetup={onBuildSetup}
      onOpenTicker={vi.fn()}
      onCompare={vi.fn()}
      onOpenEdge={vi.fn()}
    />,
  );
const served = (description: string | null, mine: boolean) => {
  hooks.runs.mockReturnValue({
    data: { session: null, byId: new Map([['my-vrp', { id: 'my-vrp', description }]]) },
  });
  hooks.mine.mockReturnValue({ data: mine ? [{ screenerId: 'my-vrp' }] : [] });
};

describe('TestResultPage', () => {
  beforeEach(() => {
    served(null, false);
  });

  it('shows the description under the name', () => {
    served('Rich premium in calm names', true);
    renderPage();
    expect(screen.getByText('Rich premium in calm names')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add a description' })).toBeNull();
  });

  it('offers "Add a description" to the owner of a screener without one, not for a preset', async () => {
    const onEdit = vi.fn();
    served(null, true);
    const view = renderPage(onEdit);
    await userEvent.click(screen.getByRole('button', { name: 'Add a description' }));
    expect(onEdit).toHaveBeenCalledOnce();
    view.unmount();
    served(null, false);
    renderPage();
    expect(screen.queryByRole('button', { name: 'Add a description' })).toBeNull();
  });

  it('Edit criteria goes straight to the Builder, with no drawer first', async () => {
    const onEdit = vi.fn();
    const onBuildSetup = vi.fn();
    render(
      <TestResultPage
        id="my-vrp"
        f={undefined}
        onFilterChange={vi.fn()}
        onEdit={onEdit}
        onBuildSetup={onBuildSetup}
        onOpenTicker={vi.fn()}
        onCompare={vi.fn()}
        onOpenEdge={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'my-vrp' })).toBeInTheDocument();
    expect(screen.getByText('results')).toBeInTheDocument();
    expect(screen.getByText('edge line of my-vrp')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Edit criteria' }));
    expect(onEdit).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Test it as a setup' }));
    expect(onBuildSetup).toHaveBeenCalledOnce();
    expect(screen.getByRole('navigation', { name: 'Test steps' })).toHaveTextContent('Result');
  });
});
