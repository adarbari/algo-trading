import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ExpandableTable, type ExpandableTableColumn } from './ExpandableTable';

const COLUMNS: ExpandableTableColumn[] = [
  { id: 'name', label: 'Screener', grow: 2, narrow: true },
  { id: 'picks', label: 'Picks today', align: 'end', narrow: true },
  { id: 'run', label: 'Last run' },
];

const row = (id: string, open = false, onOpenChange = vi.fn()) => ({
  id,
  cells: { name: id, picks: '12', run: '2026-10-07' },
  open,
  onOpenChange,
  detail: `detail of ${id}`,
});

describe('ExpandableTable', () => {
  it('names the table, its headers and the toggle of each row', () => {
    render(<ExpandableTable label="Screeners" columns={COLUMNS} rows={[row('a'), row('b')]} />);
    expect(screen.getByRole('table', { name: 'Screeners' })).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Screener',
      'Picks today',
      'Last run',
    ]);
    expect(screen.getByRole('button', { name: 'a' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('reports the requested state from the toggle and renders the detail only while open', async () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <ExpandableTable
        label="Screeners"
        columns={COLUMNS}
        rows={[row('a', false, onOpenChange)]}
      />,
    );
    expect(screen.queryByText('detail of a')).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'a' }));
    expect(onOpenChange).toHaveBeenCalledWith(true);
    rerender(
      <ExpandableTable label="Screeners" columns={COLUMNS} rows={[row('a', true, onOpenChange)]} />,
    );
    expect(screen.getByText('detail of a')).toBeVisible();
    expect(screen.getByRole('button', { name: 'a' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens with Enter from the keyboard', async () => {
    const onOpenChange = vi.fn();
    render(
      <ExpandableTable
        label="Screeners"
        columns={COLUMNS}
        rows={[row('a', false, onOpenChange)]}
      />,
    );
    await userEvent.setup().tab();
    await userEvent.keyboard('{Enter}');
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ExpandableTable label="Screeners" columns={COLUMNS} rows={[row('a', true), row('b')]} />,
    );
    await expectNoA11yViolations(container);
  });
});
