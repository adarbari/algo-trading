import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import type { TableViewState } from '../model/table-view';

import { ViewControls } from './ViewControls';

function state(patch: Partial<TableViewState> = {}): TableViewState {
  return {
    scope: 'screener:vrp',
    name: null,
    names: ['Earnings'],
    ready: true,
    columns: [],
    narrowColumns: [],
    sort: null,
    decisions: null,
    change: vi.fn(),
    select: vi.fn(),
    saveAs: vi.fn(),
    remove: vi.fn(),
    saving: false,
    removing: false,
    error: null,
    ...patch,
  };
}

describe('ViewControls', () => {
  it('switches views and names the current choice as a new one', async () => {
    const view = state();
    const { container } = render(<ViewControls view={view} />);
    expect(screen.queryByRole('button', { name: 'Delete view' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Save view as…' }));
    const dialog = screen.getByRole('dialog', { name: 'Save view as' });
    await userEvent.type(screen.getByRole('textbox'), ' Mine ');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(view.saveAs).toHaveBeenCalledWith('Mine', expect.any(Function));
    expect(dialog).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('removes a named view in use', async () => {
    const view = state({ name: 'Earnings' });
    render(<ViewControls view={view} />);
    await userEvent.click(screen.getByRole('button', { name: 'Delete view' }));
    expect(view.remove).toHaveBeenCalled();
  });

  it('says why a save was refused', async () => {
    const view = state({ error: new Error('view.columns: no such feature') });
    render(<ViewControls view={view} />);
    await userEvent.click(screen.getByRole('button', { name: 'Save view as…' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('view.columns: no such feature');
  });
});
