import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { FilterDefinition } from '@/entities/filter';
import type { TableViewState } from '@/entities/saved-view';
import { expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import type { FilterStateApi } from '../api/use-filter-state';
import { ViewsMenu } from './ViewsMenu';

const DEFINITIONS: FilterDefinition[] = [
  {
    id: 'decision',
    label: 'Decision',
    group: 'SETUP',
    kind: 'PICK',
    guide: 'term:filter_decision',
    options: [{ value: 'QUALIFIED', label: 'Qualified' }],
    bins: [],
    windowUnit: null,
    unit: null,
  },
];

const HELD: Record<string, string> = {
  Calm: 'decision:QUALIFIED',
  Stale: 'gone:x;decision:QUALIFIED',
};

function fakeView(patch: Partial<TableViewState> = {}): TableViewState {
  return {
    scope: 'surface:ideas',
    name: null,
    names: ['Calm', 'Stale'],
    named: Object.entries(HELD).map(([name, filters]) => ({ name, filters })),
    ready: true,
    columns: [],
    narrowColumns: [],
    sort: null,
    decisions: null,
    droppedFilters: [],
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

const state = {
  filters: [{ id: 'decision', values: ['QUALIFIED'], active: true }],
  f: 'decision:QUALIFIED',
} as unknown as FilterStateApi;

stubElementSize();

function setup(view: TableViewState) {
  const done = render(
    <ViewsMenu view={view} state={state} definitions={DEFINITIONS} labelOf={undefined} />,
  );
  return done;
}

describe('ViewsMenu', () => {
  it('lists each saved view with the filters it holds, in the chips’ words', async () => {
    const user = userEvent.setup();
    const { container } = setup(fakeView());
    await user.click(screen.getByRole('button', { name: 'Views · 2' }));
    const menu = await screen.findByRole('dialog', { name: 'Views' });
    expect(
      await within(menu).findByRole('button', { name: /^Calm\s*Decision Qualified/ }),
    ).toBeVisible();
    expect(
      within(menu).getByRole('button', { name: /^Stale\s*gone x · Decision Qualified/ }),
    ).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('applies a view, a default view, and deletes one by name', async () => {
    const user = userEvent.setup();
    const view = fakeView();
    setup(view);
    await user.click(screen.getByRole('button', { name: 'Views · 2' }));
    await user.click(await screen.findByRole('button', { name: /^Calm/ }));
    expect(view.select).toHaveBeenCalledWith('Calm');
    await user.click(screen.getByRole('button', { name: 'Views · 2' }));
    await user.click(await screen.findByRole('button', { name: 'Delete view Stale' }));
    expect(view.remove).toHaveBeenCalledWith('Stale');
    await user.click(screen.getByRole('button', { name: 'Default view' }));
    expect(view.select).toHaveBeenLastCalledWith(null);
  });

  it('saves the current filters under a name, shows them, and says Replace for a taken name', async () => {
    const user = userEvent.setup();
    const view = fakeView();
    setup(view);
    await user.click(screen.getByRole('button', { name: 'Views · 2' }));
    const menu = await screen.findByRole('dialog', { name: 'Views' });
    // the popover moves focus in when it opens; typing before that is lost
    await waitFor(() => {
      expect(menu.contains(document.activeElement)).toBe(true);
    });
    await user.type(within(menu).getByRole('textbox', { name: 'Name of the view' }), 'Fresh');
    expect(within(menu).getAllByText('Decision Qualified').length).toBeGreaterThan(0);
    await user.click(within(menu).getByRole('button', { name: 'Save view' }));
    expect(view.saveAs).toHaveBeenCalledWith('Fresh', expect.any(Function));
    await user.clear(within(menu).getByRole('textbox', { name: 'Name of the view' }));
    await user.type(within(menu).getByRole('textbox', { name: 'Name of the view' }), 'Calm');
    expect(within(menu).getByRole('button', { name: 'Replace view' })).toBeEnabled();
  });

  it('names the filters a view applied without, because the surface no longer defines them', () => {
    setup(fakeView({ droppedFilters: ['gone'] }));
    expect(screen.getByText('Not applied · 1')).toBeVisible();
    expect(screen.getByText('gone')).toBeVisible();
  });
});
