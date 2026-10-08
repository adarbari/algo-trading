import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import type { DataTableColumn } from './columns';
import { DataTable, type DataTableProps } from './DataTable';
import { makeUniverse, type TickerRow } from './storyData';

const columns: DataTableColumn<TickerRow>[] = [
  { id: 'symbol', header: 'Ticker', value: (r) => r.symbol, mono: true, hideable: false },
  { id: 'close', header: 'Close', value: (r) => r.close, format: { kind: 'currency' } },
  {
    id: 'iv30',
    header: 'IV30',
    description: 'Our 30-day implied volatility',
    value: (r) => r.iv30,
    format: { kind: 'percent' },
  },
  {
    id: 'fromHigh',
    header: 'From high',
    value: (r) => r.fromHigh,
    format: { kind: 'delta', digits: 1 },
  },
  { id: 'adv', header: 'ADV', value: (r) => r.adv, format: { kind: 'currency-compact' } },
];

const rows = makeUniverse(5);

function Table(props: Partial<DataTableProps<TickerRow>>) {
  return (
    <DataTable columns={columns} rows={rows} getRowId={(r) => r.id} label="Tickers" {...props} />
  );
}

function Selectable(
  props: Partial<DataTableProps<TickerRow>> & { onChange?: (ids: string[]) => void },
) {
  const { onChange, ...rest } = props;
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <Table
      selectable
      selectedIds={selected}
      getRowLabel={(r) => r.symbol}
      onSelectionChange={(ids) => {
        setSelected(ids);
        onChange?.(ids);
      }}
      {...rest}
    />
  );
}

/** The item at `index`, failing the test when it is missing. */
function at<T>(items: readonly T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`no item at ${index}`);
  return item;
}

const bodyRows = () =>
  screen.getAllByRole('row').filter((row) => row.getAttribute('aria-rowindex') !== '1');
const firstCells = () =>
  bodyRows().map((row) => within(row).getAllByRole('gridcell')[0]?.textContent);

// jsdom has no layout: give elements a size so the virtualizer has a viewport to fill.
const sized = ['offsetHeight', 'offsetWidth'] as const;
const originals = sized.map((key) => Object.getOwnPropertyDescriptor(HTMLElement.prototype, key));
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get: () => 400,
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get: () => 1000,
  });
});
afterAll(() => {
  sized.forEach((key, i) => {
    const original = originals[i];
    if (original) Object.defineProperty(HTMLElement.prototype, key, original);
  });
});

describe('DataTable', () => {
  it('renders an ARIA grid with headers and formatted, aligned cells', () => {
    render(<Table />);
    const grid = screen.getByRole('grid', { name: 'Tickers' });
    expect(grid).toHaveAttribute('aria-rowcount', '6');
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Ticker',
      'Close',
      'IV30Our 30-day implied volatility',
      'From high',
      'ADV',
    ]);
    const aapl = at(bodyRows(), 0);
    const cells = within(aapl).getAllByRole('gridcell');
    expect(cells.map((c) => c.textContent)).toEqual([
      'AAPL',
      '$333.69',
      '24.4%',
      '−3.4%',
      '$13.99B',
    ]);
    expect(cells[1]).toHaveAttribute('data-align', 'end');
    expect(cells[3]).toHaveAttribute('data-tone', 'down');
  });

  it('sorts on header click with aria-sort; numbers start high-first, text A-Z', async () => {
    const onSortChange = vi.fn();
    render(<Table onSortChange={onSortChange} />);
    const user = userEvent.setup();
    const closeHeader = screen.getByRole('columnheader', { name: /Close/ });
    expect(closeHeader).toHaveAttribute('aria-sort', 'none');
    await user.click(within(closeHeader).getByRole('button'));
    expect(closeHeader).toHaveAttribute('aria-sort', 'descending');
    expect(onSortChange).toHaveBeenLastCalledWith({ columnId: 'close', direction: 'desc' });
    expect(firstCells()).toEqual(['SPY', 'QQQ', 'MSFT', 'AAPL', 'NVDA']);
    await user.click(within(closeHeader).getByRole('button'));
    expect(closeHeader).toHaveAttribute('aria-sort', 'ascending');
    expect(firstCells()).toEqual(['NVDA', 'AAPL', 'MSFT', 'QQQ', 'SPY']);
    const ticker = screen.getByRole('columnheader', { name: /Ticker/ });
    await user.click(within(ticker).getByRole('button'));
    expect(ticker).toHaveAttribute('aria-sort', 'ascending');
    expect(closeHeader).toHaveAttribute('aria-sort', 'none');
    expect(firstCells()).toEqual(['AAPL', 'MSFT', 'NVDA', 'QQQ', 'SPY']);
  });

  it('leaves the order to the caller in server sort mode, still reporting the sort', async () => {
    const onSortChange = vi.fn();
    render(<Table sortMode="server" onSortChange={onSortChange} />);
    const closeHeader = screen.getByRole('columnheader', { name: /Close/ });
    await userEvent.setup().click(within(closeHeader).getByRole('button'));
    expect(closeHeader).toHaveAttribute('aria-sort', 'descending');
    expect(onSortChange).toHaveBeenLastCalledWith({ columnId: 'close', direction: 'desc' });
    expect(firstCells()).toEqual(rows.map((r) => r.symbol)); // the rows as given
  });

  it('keeps missing values last in both directions', async () => {
    const withGap = [...rows, { ...at(rows, 0), id: 'NOIV', symbol: 'NOIV', iv30: null }];
    render(<Table rows={withGap} defaultSort={{ columnId: 'iv30', direction: 'desc' }} />);
    expect(firstCells().at(-1)).toBe('NOIV');
    await userEvent
      .setup()
      .click(within(screen.getByRole('columnheader', { name: /IV30/ })).getByRole('button'));
    expect(firstCells().at(-1)).toBe('NOIV');
  });

  it('follows a controlled sort', () => {
    render(<Table sort={{ columnId: 'adv', direction: 'asc' }} />);
    expect(firstCells()).toEqual(['MSFT', 'AAPL', 'QQQ', 'NVDA', 'SPY']);
  });

  it('selects rows with checkboxes, Shift-click ranges and select-all (controlled)', async () => {
    const onChange = vi.fn();
    render(<Selectable onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('checkbox', { name: 'Select AAPL' }));
    expect(onChange).toHaveBeenLastCalledWith(['AAPL']);
    expect(bodyRows()[0]).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{Shift>}');
    await user.click(screen.getByRole('checkbox', { name: 'Select NVDA' }));
    await user.keyboard('{/Shift}');
    expect([...(onChange.mock.lastCall?.[0] as string[])].sort()).toEqual(['AAPL', 'MSFT', 'NVDA']);
    const all = screen.getByRole('checkbox', { name: 'Select all rows' });
    expect((all as HTMLInputElement).indeterminate).toBe(true);
    await user.click(all);
    expect(onChange.mock.lastCall?.[0] as string[]).toHaveLength(5);
    expect(all).toBeChecked();
  });

  it('moves the active row with the keyboard; Enter activates, Space selects', async () => {
    const onRowActivate = vi.fn();
    const onChange = vi.fn();
    render(<Selectable onRowActivate={onRowActivate} onChange={onChange} />);
    const user = userEvent.setup();
    const grid = screen.getByRole('grid');
    await user.tab();
    expect(grid).toHaveFocus();
    expect(grid.getAttribute('aria-activedescendant')).toBe(at(bodyRows(), 0).id);
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(grid.getAttribute('aria-activedescendant')).toBe(at(bodyRows(), 2).id);
    await user.keyboard('{Enter}');
    expect(onRowActivate).toHaveBeenLastCalledWith(expect.objectContaining({ symbol: 'NVDA' }));
    await user.keyboard(' ');
    expect(onChange).toHaveBeenLastCalledWith(['NVDA']);
    await user.keyboard('{End}');
    expect(grid.getAttribute('aria-activedescendant')).toBe(at(bodyRows(), 4).id);
    await user.keyboard('{Home}');
    expect(grid.getAttribute('aria-activedescendant')).toBe(at(bodyRows(), 0).id);
    await user.click(at(within(at(bodyRows(), 1)).getAllByRole('gridcell'), 1));
    expect(onRowActivate).toHaveBeenLastCalledWith(expect.objectContaining({ symbol: 'MSFT' }));
  });

  it('renders toolbarEnd in the same group as the column picker', () => {
    render(<Table columnPicker toolbarEnd={<button type="button">Catalogue</button>} />);
    const end = screen.getByRole('button', { name: 'Catalogue' }).parentElement;
    expect(end).toContainElement(screen.getByRole('button', { name: /Columns/ }));
  });

  it('hides and shows columns from the picker, with descriptions', async () => {
    const onHidden = vi.fn();
    render(<Table columnPicker defaultHiddenColumns={['adv']} onHiddenColumnsChange={onHidden} />);
    const user = userEvent.setup();
    expect(screen.queryByRole('columnheader', { name: 'ADV' })).toBeNull();
    const button = screen.getByRole('button', { name: /Columns/ });
    expect(button).toHaveTextContent('4 of 5');
    await user.click(button);
    const panel = screen.getByRole('group', { name: 'Show columns' });
    const iv = within(panel).getByRole('checkbox', { name: 'IV30' });
    expect(iv).toHaveAccessibleDescription('Our 30-day implied volatility');
    expect(within(panel).getByRole('checkbox', { name: 'Ticker' })).toBeDisabled();
    await user.click(within(panel).getByRole('checkbox', { name: 'ADV' }));
    expect(onHidden).toHaveBeenLastCalledWith([]);
    expect(screen.getByRole('columnheader', { name: 'ADV' })).toBeInTheDocument();
    await user.click(iv);
    expect(onHidden).toHaveBeenLastCalledWith(['iv30']);
    await user.keyboard('{Escape}');
    expect(panel).not.toBeVisible();
    expect(button).toHaveFocus();
  });

  it('renders cell slots with the row, raw and formatted value', () => {
    const slot = vi.fn(({ formatted }: { formatted: { text: string } }) => (
      <b>{formatted.text}!</b>
    ));
    render(<Table columns={[{ ...at(columns, 1), cell: slot }]} rows={rows.slice(0, 1)} />);
    expect(screen.getByText('$333.69!')).toBeInTheDocument();
    expect(slot).toHaveBeenCalledWith(expect.objectContaining({ row: rows[0], value: 333.69 }));
  });

  it('shows loading placeholders, the empty message and errors', () => {
    const { rerender } = render(<Table status="loading" />);
    expect(screen.getByRole('grid')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('AAPL')).toBeNull();
    rerender(<Table rows={[]} emptyMessage="No names pass" />);
    expect(screen.getByRole('gridcell', { name: 'No names pass' })).toBeInTheDocument();
    rerender(<Table status="error" errorMessage="Preview failed" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Preview failed');
  });

  it('virtualises large row sets: renders a window, not every row', () => {
    render(<Table rows={makeUniverse(11_427)} visibleRows={12} />);
    expect(screen.getByRole('grid')).toHaveAttribute('aria-rowcount', '11428');
    expect(bodyRows().length).toBeLessThan(40);
  });

  it('pins the checkbox and first columns at the start, header and rows alike', () => {
    render(<Selectable />);
    const grid = screen.getByRole('grid');
    const [header, firstRow] = within(grid).getAllByRole('row');
    const pins = (row: HTMLElement | undefined) =>
      Array.from(row?.children ?? []).map((cell) => cell.getAttribute('data-pinned'));
    expect(pins(header)).toEqual(['select', 'first', null, null, null, null]);
    expect(pins(firstRow)).toEqual(['select', 'first', null, null, null, null]);
  });

  it('pins nothing with pinFirst false, and marks the grid scrolled sideways', () => {
    render(<Table pinFirst={false} />);
    const grid = screen.getByRole('grid');
    expect(grid.querySelector('[data-pinned]')).toBeNull();
    grid.scrollLeft = 40;
    grid.dispatchEvent(new Event('scroll'));
    expect(grid).toHaveAttribute('data-scrolled-x');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Selectable columnPicker />);
    await expectNoA11yViolations(container);
  });

  it('tints a cell from its row, with the value still readable', async () => {
    const fill = (r: TickerRow) =>
      r.symbol === rows[0]?.symbol ? ('warning' as const) : undefined;
    const tinted = columns.map((c) => (c.id === 'iv30' ? { ...c, fill } : c));
    const { container } = render(<Table columns={tinted} />);
    const cells = container.querySelectorAll('[data-fill]');
    expect(cells).toHaveLength(1);
    expect(cells[0]).toHaveAttribute('data-fill', 'warning');
    expect(cells[0]?.textContent).toMatch(/%/);
    await expectNoA11yViolations(container);
  });

  it('moves the active row with j / k and arrows, reporting each change', async () => {
    const onActiveRowChange = vi.fn();
    render(<Table onActiveRowChange={onActiveRowChange} />);
    screen.getByRole('grid', { name: 'Tickers' }).focus(); // focusing makes the first row active
    await userEvent.keyboard('jjk');
    expect(onActiveRowChange.mock.calls.map(([row]) => (row as TickerRow).symbol)).toEqual(
      [0, 1, 2, 1].map((i) => rows[i]?.symbol),
    );
    await userEvent.keyboard('{ArrowUp}');
    expect(onActiveRowChange).toHaveBeenCalledTimes(5);
  });

  it("runs the caller's keys on the active row, and leaves j / k to a caller that binds them", async () => {
    const onC = vi.fn();
    const onJ = vi.fn();
    const onActiveRowChange = vi.fn();
    render(<Table rowKeys={{ c: onC, j: onJ }} onActiveRowChange={onActiveRowChange} />);
    screen.getByRole('grid', { name: 'Tickers' }).focus();
    await userEvent.keyboard('{ArrowDown}c');
    expect(onC).toHaveBeenCalledWith(rows[1]);
    await userEvent.keyboard('j');
    expect(onJ).toHaveBeenCalledWith(rows[1]);
    expect(onActiveRowChange).toHaveBeenCalledTimes(2); // focus, ArrowDown: j did not move it
  });

  it('marks rows clickable only when a click acts on them (open, or focus for a detail)', () => {
    const clickable = () => bodyRows().map((row) => row.hasAttribute('data-clickable'));
    const none = rows.map(() => false);
    const all = rows.map(() => true);
    const { rerender } = render(<Table />);
    expect(clickable()).toEqual(none);
    rerender(<Table onRowActivate={vi.fn()} />);
    expect(clickable()).toEqual(all);
    rerender(<Table onRowActivate={vi.fn()} activateOnClick={false} />);
    expect(clickable()).toEqual(none);
    rerender(<Table activateOnClick={false} onActiveRowChange={vi.fn()} />);
    expect(clickable()).toEqual(all);
  });

  it('can make a click only select the row, and the caller can control the active row', async () => {
    const onRowActivate = vi.fn();
    const onActiveRowChange = vi.fn();
    const target = rows[2];
    if (!target) throw new Error('rows');
    const { container } = render(
      <Table
        onRowActivate={onRowActivate}
        activateOnClick={false}
        onActiveRowChange={onActiveRowChange}
        activeRowId={rows[0]?.id ?? null}
      />,
    );
    await userEvent.click(screen.getByText(target.symbol));
    expect(onActiveRowChange).toHaveBeenCalledWith(target);
    expect(onRowActivate).not.toHaveBeenCalled();
    const active = container.querySelector('[data-active]');
    expect(active?.getAttribute('data-row-id')).toBe(rows[0]?.id); // controlled: the caller decides
  });

  it('shows a header action beside the sort button, not inside it', async () => {
    const onAction = vi.fn();
    const helped = columns.map((c) =>
      c.id === 'iv30'
        ? {
            ...c,
            headerAction: (
              <button type="button" aria-label="What is IV30?" onClick={onAction}>
                i
              </button>
            ),
          }
        : c,
    );
    const { container } = render(<Table columns={helped} />);
    const header = screen.getByRole('columnheader', { name: /IV30/ });
    const action = within(header).getByRole('button', { name: 'What is IV30?' });
    expect(action.closest('button[aria-describedby]')).toBeNull(); // not inside the sort button
    await userEvent.click(action);
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(header.getAttribute('aria-sort')).toBe('none'); // the action did not sort
    await expectNoA11yViolations(container);
  });
});

describe('DataTable on a narrow width', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the essential columns, the rest wait in the picker until added back', async () => {
    vi.stubGlobal('innerWidth', 375);
    const columns: DataTableColumn<TickerRow>[] = [
      { id: 'symbol', header: 'Symbol', value: (r) => r.symbol, hideable: false },
      { id: 'name', header: 'Name', value: (r) => r.name },
      { id: 'close', header: 'Close', value: (r) => r.close, essential: true },
      { id: 'adv', header: 'ADV', value: (r) => r.adv },
    ];
    render(<Table columns={columns} />);
    const headers = () => screen.getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers()).toEqual(['Symbol', 'Close']);
    const button = screen.getByRole('button', { name: /Columns/ });
    expect(button).toHaveTextContent('2 of 4');
    await userEvent.click(button);
    await userEvent.click(screen.getByRole('checkbox', { name: 'ADV' }));
    expect(headers()).toEqual(['Symbol', 'Close', 'ADV']);
  });

  it('takes the added-back columns from narrowColumns and reports a new one', async () => {
    vi.stubGlobal('innerWidth', 375);
    const columns: DataTableColumn<TickerRow>[] = [
      { id: 'symbol', header: 'Symbol', value: (r) => r.symbol, hideable: false },
      { id: 'name', header: 'Name', value: (r) => r.name },
      { id: 'close', header: 'Close', value: (r) => r.close, essential: true },
      { id: 'adv', header: 'ADV', value: (r) => r.adv },
    ];
    const onChange = vi.fn();
    render(
      <Table columns={columns} narrowColumns={['name', 'nope']} onNarrowColumnsChange={onChange} />,
    );
    const headers = () => screen.getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers()).toEqual(['Symbol', 'Name', 'Close']);
    await userEvent.click(screen.getByRole('button', { name: /Columns/ }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'ADV' }));
    expect(onChange).toHaveBeenCalledWith(['name', 'nope', 'adv']);
    expect(headers()).toEqual(['Symbol', 'Name', 'Close']); // controlled: the caller decides
  });

  it('keeps the first three columns when none is marked essential', () => {
    vi.stubGlobal('innerWidth', 375);
    const columns: DataTableColumn<TickerRow>[] = [
      { id: 'symbol', header: 'Symbol', value: (r) => r.symbol },
      { id: 'name', header: 'Name', value: (r) => r.name },
      { id: 'close', header: 'Close', value: (r) => r.close },
      { id: 'adv', header: 'ADV', value: (r) => r.adv },
    ];
    render(<Table columns={columns} />);
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Symbol',
      'Name',
      'Close',
    ]);
  });

  it('shows every column on a wide width', () => {
    vi.stubGlobal('innerWidth', 1400);
    const columns: DataTableColumn<TickerRow>[] = [
      { id: 'symbol', header: 'Symbol', value: (r) => r.symbol },
      { id: 'name', header: 'Name', value: (r) => r.name },
      { id: 'close', header: 'Close', value: (r) => r.close, essential: true },
      { id: 'adv', header: 'ADV', value: (r) => r.adv },
    ];
    render(<Table columns={columns} />);
    expect(screen.getAllByRole('columnheader')).toHaveLength(4);
    expect(screen.queryByRole('button', { name: /Columns/ })).toBeNull();
  });
});
