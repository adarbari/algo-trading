import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SUMMARIES_FIXTURE } from '@/entities/screener-run';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ScreenerRunList } from './ScreenerRunList';

const hooks = vi.hoisted(() => ({ useScreenerRuns: vi.fn() }));
vi.mock('@/entities/screener-run', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerRuns: hooks.useScreenerRuns,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text>,
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
  };
});

stubElementSize();

beforeEach(() => {
  hooks.useScreenerRuns.mockReturnValue(fakeQuery(SUMMARIES_FIXTURE));
});

describe('ScreenerRunList', () => {
  it('lists each run with its Guide buttons; unrecorded figures stay empty', async () => {
    const { container } = render(<ScreenerRunList selected={null} onSelect={vi.fn()} />);
    const table = screen.getByRole('grid', { name: 'Screener runs' });
    const done = within(table).getByRole('row', { name: /trend_pullback/ });
    expect(within(done).getByText('complete')).toBeInTheDocument();
    expect(within(done).getByText('12')).toBeInTheDocument();
    expect(within(done).getByText('Risk on')).toBeInTheDocument();
    const failed = within(table).getByRole('row', { name: /value_dip/ });
    expect(within(failed).getByText('failed')).toBeInTheDocument();
    expect(within(failed).queryByText('0')).not.toBeInTheDocument();
    expect(screen.getByText('help screener_run_status')).toBeInTheDocument();
    expect(screen.getByText('help screener_run_picked')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('selects a run on a row click', async () => {
    const onSelect = vi.fn();
    render(<ScreenerRunList selected={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('row', { name: /trend_pullback/ }));
    expect(onSelect).toHaveBeenCalledWith('screen-trend-site-1');
  });

  it('sends the screener typed on Enter, keeping the other filters', async () => {
    const onFiltersChange = vi.fn();
    render(
      <ScreenerRunList
        selected={null}
        onSelect={vi.fn()}
        filters={{ status: 'failed' }}
        onFiltersChange={onFiltersChange}
      />,
    );
    await userEvent.type(screen.getByRole('searchbox', { name: 'Screener' }), 'trend{Enter}');
    expect(onFiltersChange).toHaveBeenCalledWith({ status: 'failed', screener: 'trend' });
  });

  it('shows the loading, error and empty states', () => {
    hooks.useScreenerRuns.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<ScreenerRunList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('Loading screener runs…')).toBeInTheDocument();
    hooks.useScreenerRuns.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<ScreenerRunList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('The screener runs failed to load.')).toBeInTheDocument();
    hooks.useScreenerRuns.mockReturnValue(fakeQuery([]));
    rerender(<ScreenerRunList selected={null} onSelect={vi.fn()} filters={{ user: 'x' }} />);
    expect(screen.getByText('No run matches these filters.')).toBeInTheDocument();
    rerender(<ScreenerRunList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('No screener run is recorded.')).toBeInTheDocument();
  });
});
