import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { HeatGrid, type HeatGridRow } from './HeatGrid';

const columns = [
  { id: 'd1', label: 'Oct 1' },
  { id: 'd2', label: 'Oct 2' },
];
const rows: HeatGridRow[] = [
  {
    id: 'bars',
    label: 'Daily bars',
    cells: { d1: { status: 'complete', text: '100' }, d2: { status: 'failed', text: '0' } },
  },
  { id: 'chains', label: 'Option chains', cells: { d2: { status: 'partial', text: '86' } } },
];

describe('HeatGrid', () => {
  it('renders an ARIA grid with column and row headers and described cells', () => {
    render(<HeatGrid label="Completeness" rowHeader="Dataset" rows={rows} columns={columns} />);
    expect(screen.getByRole('grid', { name: 'Completeness' })).toHaveAttribute(
      'aria-rowcount',
      '3',
    );
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Dataset',
      'Oct 1',
      'Oct 2',
    ]);
    expect(screen.getAllByRole('rowheader').map((h) => h.textContent)).toEqual([
      'Daily bars',
      'Option chains',
    ]);
    expect(
      screen.getByRole('gridcell', { name: 'Option chains, Oct 1: not collected' }),
    ).toHaveAttribute('data-tone', 'empty');
    expect(
      screen.getByRole('gridcell', { name: 'Option chains, Oct 2: partial 86' }),
    ).toHaveAttribute('data-tone', 'warning');
  });

  it('marks the selected cell and puts only it in the Tab order', () => {
    render(
      <HeatGrid
        label="G"
        rows={rows}
        columns={columns}
        selected={{ row: 'chains', column: 'd2' }}
      />,
    );
    const cell = screen.getByRole('gridcell', { name: /Option chains, Oct 2/ });
    expect(cell).toHaveAttribute('aria-selected', 'true');
    expect(cell).toHaveAttribute('tabindex', '0');
    expect(screen.getAllByRole('gridcell').filter((c) => c.tabIndex === 0)).toHaveLength(1);
  });

  it('moves with the arrow keys and Home / End, selects with Enter, Space and click', async () => {
    const onSelect = vi.fn();
    render(<HeatGrid label="G" rows={rows} columns={columns} onSelect={onSelect} />);
    const user = userEvent.setup();
    await user.tab();
    expect(screen.getByRole('gridcell', { name: /Daily bars, Oct 1/ })).toHaveFocus();
    await user.keyboard('{ArrowRight}{ArrowDown}');
    expect(screen.getByRole('gridcell', { name: /Option chains, Oct 2/ })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenLastCalledWith({ row: 'chains', column: 'd2' });
    await user.keyboard('{Home}');
    expect(screen.getByRole('gridcell', { name: /Option chains, Oct 1/ })).toHaveFocus();
    await user.keyboard('{ArrowUp}{ArrowUp}{End} ');
    expect(onSelect).toHaveBeenLastCalledWith({ row: 'bars', column: 'd2' });
    await user.click(screen.getByRole('gridcell', { name: /Option chains, Oct 1/ }));
    expect(onSelect).toHaveBeenLastCalledWith({ row: 'chains', column: 'd1' });
  });

  it('shows a legend of the four statuses, with custom words', () => {
    render(
      <HeatGrid
        label="G"
        rows={rows}
        columns={columns}
        statusLabels={{ 'not-collected': 'no source' }}
      />,
    );
    expect(screen.getByRole('list', { name: 'Status key' })).toHaveTextContent(
      'completepartialfailedno source',
    );
  });

  it('shows loading, empty and error states', () => {
    const { rerender } = render(<HeatGrid label="G" rows={rows} columns={columns} loading />);
    expect(screen.getByRole('grid')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('86')).toBeNull();
    rerender(<HeatGrid label="G" rows={[]} columns={columns} emptyMessage="No sessions" />);
    expect(screen.getByText('No sessions')).toBeInTheDocument();
    rerender(<HeatGrid label="G" rows={rows} columns={columns} error="Failed" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Failed');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <HeatGrid
        label="Completeness"
        rows={rows}
        columns={columns}
        selected={{ row: 'bars', column: 'd1' }}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
