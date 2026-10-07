import type { Meta, StoryObj } from '@storybook/react-vite';
import { useMemo, useState } from 'react';
import { expect, userEvent, within } from 'storybook/test';

import { narrow } from '../../testing';
import { Mono } from '../../primitives/Mono';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { StatusBadge } from '../StatusBadge';
import type { DataTableColumn } from './columns';
import { DataTable, type DataTableProps } from './DataTable';
import { makeUniverse, screenRows, type ScreenRow, type TickerRow } from './storyData';

const DECISION_TONE = { QUALIFIED: 'positive', WATCH: 'accent', EVENT_RISK: 'warning' } as const;

/** The screener preview table from the approved Screener mockup. */
const screenColumns: DataTableColumn<ScreenRow>[] = [
  { id: 'symbol', header: 'Symbol', value: (r) => r.symbol, mono: true, width: 'sm' },
  {
    id: 'decision',
    header: 'Decision',
    value: (r) => r.decision,
    width: 'sm',
    // A cell slot: the decision as a StatusBadge (the text says the state; colour reinforces it).
    cell: ({ row }) => (
      <StatusBadge tone={DECISION_TONE[row.decision]}>{row.decision.replace('_', ' ')}</StatusBadge>
    ),
  },
  { id: 'score', header: 'Score', value: (r) => r.score, format: { kind: 'number' }, width: 'xs' },
  {
    id: 'iv30',
    header: 'IV30',
    description: 'Our 30-day ATM implied volatility',
    value: (r) => r.iv30,
    format: { kind: 'percent' },
  },
  {
    id: 'hv30',
    header: 'HV30',
    description: '30-day realised volatility',
    value: (r) => r.hv30,
    format: { kind: 'percent' },
  },
  {
    id: 'spread',
    header: 'IV − HV',
    value: (r) => r.spread,
    format: { kind: 'delta', unit: 'points' },
  },
  { id: 'ratio', header: 'IV / HV', value: (r) => r.ratio, format: { kind: 'number', digits: 2 } },
  {
    id: 'fromHigh',
    header: 'From 52w high',
    value: (r) => r.fromHigh,
    format: { kind: 'delta', digits: 1 },
    width: 'md',
  },
  {
    id: 'adv',
    header: 'ADV',
    description: 'Average daily dollar volume, 20 sessions',
    value: (r) => r.adv,
    format: { kind: 'currency-compact' },
  },
  {
    id: 'earnings',
    header: 'Earnings',
    description: 'Sessions to the next earnings report',
    value: (r) => r.earnings,
    format: { kind: 'number' },
  },
  {
    id: 'flags',
    header: 'Flags',
    value: (r) => r.flags,
    tone: 'muted',
    grow: true,
    sortable: false,
  },
];

/** The Explore ticker list: a two-line ticker cell and catalogue columns with descriptions. */
const tickerColumns: DataTableColumn<TickerRow>[] = [
  {
    id: 'ticker',
    header: 'Ticker',
    value: (r) => r.symbol,
    hideable: false,
    width: 'lg',
    grow: true,
    cell: ({ row }) => (
      <Stack gap={0}>
        <Mono weight="medium" size="sm">
          {row.symbol}
        </Mono>
        <Text size="xs" tone="muted" truncate>
          {row.name}
        </Text>
      </Stack>
    ),
  },
  {
    id: 'close',
    header: 'Close',
    description: 'Last close (price_stats.close)',
    value: (r) => r.close,
    format: { kind: 'currency' },
  },
  {
    id: 'iv30',
    header: 'IV30',
    description: 'Our 30-day ATM implied volatility (iv30.iv30)',
    value: (r) => r.iv30,
    format: { kind: 'percent' },
  },
  {
    id: 'ivHv',
    header: 'IV/HV',
    description: 'IV30 divided by HV30 (iv_hv_ratio)',
    value: (r) => r.ivHv,
    format: { kind: 'number', digits: 2 },
  },
  {
    id: 'fromHigh',
    header: 'From high',
    description: 'Distance below the 52-week high (pct_from_high_52w)',
    value: (r) => r.fromHigh,
    format: { kind: 'delta', digits: 1 },
  },
  {
    id: 'earnings',
    header: 'Earn.',
    description: 'Sessions to next earnings (earnings.days_to_earnings)',
    value: (r) => r.earnings,
    format: { kind: 'number' },
    width: 'xs',
  },
  {
    id: 'adv',
    header: 'ADV 20d',
    description: 'Average dollar volume over 20 sessions (price_stats.adv_usd_20d)',
    value: (r) => r.adv,
    format: { kind: 'currency-compact' },
  },
  {
    id: 'marketCap',
    header: 'Market cap',
    description: 'Shares outstanding × close (market_cap)',
    value: (r) => r.marketCap || null,
    format: { kind: 'currency-compact' },
  },
  {
    id: 'listed',
    header: 'Listed',
    description: 'First trading day (reference.list_date)',
    value: (r) => r.listed,
    format: { kind: 'date' },
    width: 'md',
  },
];

/** The same list with a one-line ticker cell (symbol only), for single-line rows. */
const oneLineColumns: DataTableColumn<TickerRow>[] = tickerColumns.map((column) =>
  column.id === 'ticker'
    ? {
        id: 'ticker',
        header: 'Ticker',
        value: (r) => r.symbol,
        hideable: false,
        mono: true,
        width: 'sm',
      }
    : column,
);

const smallUniverse = makeUniverse(40);
const fullUniverse = makeUniverse();

/** Stories own selection (controlled), as the app will. */
function TickerTable(
  props: Partial<DataTableProps<TickerRow>> & { rows: TickerRow[]; initialSelected?: string[] },
) {
  const { initialSelected = [], rows, ...rest } = props;
  const [selected, setSelected] = useState<string[]>(initialSelected);
  const toolbar = useMemo(
    () => (
      <Text size="sm" tone="muted">
        {rows.length.toLocaleString('en-US')} of 11,427 tickers · {selected.length} selected
      </Text>
    ),
    [rows.length, selected.length],
  );
  return (
    <DataTable
      columns={tickerColumns}
      rows={rows}
      getRowId={(r) => r.id}
      getRowLabel={(r) => r.symbol}
      label="Tickers"
      selectable
      selectedIds={selected}
      onSelectionChange={setSelected}
      columnPicker
      defaultHiddenColumns={['marketCap', 'listed']}
      rowLines={2}
      visibleRows={8}
      toolbar={toolbar}
      {...rest}
    />
  );
}

/** The preview's columns with two tinted: IV/HV near its threshold, IV − HV missed. */
const nearMissColumns: DataTableColumn<ScreenRow>[] = screenColumns.map((column) => {
  if (column.id === 'ratio')
    return { ...column, fill: (r) => (r.ratio < 1.3 ? 'warning' : undefined) };
  if (column.id === 'spread')
    return { ...column, fill: (r) => (r.spread < 12 ? 'negative' : undefined) };
  return column;
});

const meta = {
  title: 'Components/DataTable',
  component: DataTable,
  args: {
    columns: screenColumns,
    rows: screenRows,
    getRowId: (r: ScreenRow) => r.symbol,
    label: 'Preview results',
    defaultSort: { columnId: 'score', direction: 'desc' },
  },
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof DataTable<ScreenRow>>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Screener preview: formatted numbers, a badge slot, sorted by score. */
export const Default: Story = {};

/** A criterion's near miss (warning) and miss (down) tint the cell; the value still reads as text. */
export const NearMisses: Story = {
  render: () => (
    <DataTable
      columns={nearMissColumns}
      rows={screenRows}
      getRowId={(r) => r.symbol}
      label="Preview results"
      defaultSort={{ columnId: 'score', direction: 'desc' }}
    />
  ),
};

/** Explore ticker list: selection (controlled), two-line rows, toolbar and column picker. */
export const Selection: Story = {
  render: () => <TickerTable rows={smallUniverse} initialSelected={['AAPL', 'MSFT', 'NVDA']} />,
};

/** The column picker open: every column with its catalogue description. */
export const ColumnPicker: Story = {
  render: () => <TickerTable rows={smallUniverse.slice(0, 4)} visibleRows={4} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button', { name: /Columns/ }));
    await expect(canvas.getByRole('group', { name: 'Show columns' })).toBeVisible();
  },
};

/** 11,427 rows (the covered universe), virtualised: sort a column, scroll, Shift-click a range. */
export const Performance: Story = {
  render: () => (
    <TickerTable
      rows={fullUniverse}
      visibleRows={12}
      defaultSort={{ columnId: 'adv', direction: 'desc' }}
    />
  ),
};

export const Loading: Story = { args: { status: 'loading' } };

export const Empty: Story = {
  args: { rows: [], emptyMessage: 'No names pass the hard criteria for Fri 2 Oct' },
};

export const Error: Story = {
  args: {
    status: 'error',
    errorMessage: 'The preview failed to run. Check the criteria and try again.',
  },
};

/** Many columns in a narrow container: the table scrolls sideways under a sticky header. */
export const Dense: Story = {
  render: () => (
    <Stack gap={0}>
      <TickerTable
        rows={smallUniverse}
        columns={oneLineColumns}
        defaultHiddenColumns={[]}
        rowLines={1}
        visibleRows={6}
        columnPicker={false}
      />
    </Stack>
  ),
};

/**
 * On a phone (a 375 px container), scrolled sideways: the checkbox and ticker columns stay pinned
 * at the start, over the row's background, with an end border; the other columns slide under them.
 */
export const Narrow: Story = {
  render: () => (
    <TickerTable
      rows={smallUniverse}
      initialSelected={['AAPL']}
      defaultHiddenColumns={[]}
      visibleRows={6}
    />
  ),
  decorators: [narrow],
  play: async ({ canvasElement }) => {
    const grid = within(canvasElement).getByRole('grid');
    grid.scrollLeft = grid.scrollWidth;
    grid.dispatchEvent(new Event('scroll'));
    await expect(grid.querySelector('[data-pinned="first"]')).not.toBeNull();
  },
};

/** Comfortable density: taller rows and wider cell padding from the density tokens. */
export const Comfortable: Story = {
  globals: { density: 'comfortable' },
};
