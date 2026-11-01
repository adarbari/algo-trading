import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { narrow } from '../../testing';
import {
  HeatGrid,
  type HeatGridCell,
  type HeatGridPosition,
  type HeatGridProps,
  type HeatGridRow,
} from './HeatGrid';

const days = [
  'Sep 21',
  'Sep 22',
  'Sep 23',
  'Sep 24',
  'Sep 25',
  'Sep 28',
  'Sep 29',
  'Sep 30',
  'Oct 1',
  'Oct 2',
];
const columns = days.map((label) => ({ id: label, label }));

const full = (text = '100'): HeatGridCell[] => days.map(() => ({ status: 'complete', text }));
const late = (last: HeatGridCell): HeatGridCell[] =>
  days.map((_, i) => (i === days.length - 1 ? last : { status: 'not-collected' }));
const row = (label: string, cells: HeatGridCell[]): HeatGridRow => ({
  id: label,
  label,
  cells: Object.fromEntries(days.map((day, i) => [day, cells[i]])),
});

const rows: HeatGridRow[] = [
  row('Universe & reference', full()),
  row('Company details', full()),
  row('Share counts', late({ status: 'partial', text: '99.7' })),
  row('Earnings calendar', late({ status: 'complete', text: '100' })),
  row(
    'Daily bars',
    full().map((cell, i) => (i === 3 ? { status: 'failed', text: '0' } : cell)),
  ),
  row('Treasury rates', full()),
  row('Corporate actions', full()),
  row('Option chains', late({ status: 'partial', text: '86' })),
  row('Price stats', full()),
  row('IV30 (ours)', late({ status: 'partial', text: '86' })),
  row('Liquidity class', full()),
  row('Market cap', full('99')),
  row('Screens', late({ status: 'partial', text: '88' })),
];

/** Stories own the selection (the component is controlled). */
function Selectable(props: HeatGridProps) {
  const [selected, setSelected] = useState<HeatGridPosition | null>(props.selected ?? null);
  return <HeatGrid {...props} selected={selected} onSelect={setSelected} />;
}

const meta = {
  title: 'Components/HeatGrid',
  component: HeatGrid,
  args: {
    rows,
    columns,
    label: 'Completeness by dataset and session',
    rowHeader: 'Dataset',
    selected: { row: 'Option chains', column: 'Oct 2' },
  },
  render: (args) => <Selectable {...args} />,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof HeatGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Ingestion completeness, last 10 sessions; Option chains on Oct 2 selected. */
export const Default: Story = {};

export const Loading: Story = { args: { loading: true, selected: null } };

export const Empty: Story = { args: { rows: [], emptyMessage: 'No sessions ingested yet' } };

export const Error: Story = {
  args: { error: 'Completeness failed to load. The run record has the details.' },
};

/** 30 sessions without value text, no legend: the month view. */
export const Dense: Story = {
  args: {
    legend: false,
    selected: null,
    columns: Array.from({ length: 30 }, (_, i) => ({ id: `d${i}`, label: String(i + 1) })),
    rows: rows.slice(0, 8).map((r, ri) => ({
      id: r.id,
      label: r.label,
      cells: Object.fromEntries(
        Array.from({ length: 30 }, (_, i) => [
          `d${i}`,
          {
            status:
              (i * 7 + ri * 3) % 23 === 0 ? 'failed' : (i + ri) % 11 === 0 ? 'partial' : 'complete',
          },
        ]),
      ),
    })),
  },
};

const yieldCell = (text: string, level: 1 | 2 | 3, sub: string, flag?: string): HeatGridCell => ({
  status: 'complete',
  text,
  level,
  sub,
  flag,
});

const yieldProps = {
  legend: false,
  label: 'Yearly rate by delta and expiry',
  rowHeader: 'How far out',
  statusLabels: { complete: 'yearly rate' },
  selected: { row: 'mid', column: 'nov6' },
  columns: [
    { id: 'oct30', label: 'Fri 30 Oct', sub: '7 days' },
    { id: 'nov6', label: 'Fri 6 Nov', sub: '14 days' },
    { id: 'nov20', label: 'Fri 20 Nov', sub: '28 days · includes report' },
  ],
  rows: [
    {
      id: 'far',
      label: 'Further out (0.15)',
      cells: {
        oct30: yieldCell('16.0%', 3, 'strike 81'),
        nov6: yieldCell('9.1%', 2, 'strike 79.5'),
        nov20: yieldCell('7.4%', 1, 'strike 76.5', 'report'),
      },
    },
    {
      id: 'mid',
      label: 'Middle (0.20)',
      cells: {
        oct30: yieldCell('22.2%', 3, 'strike 81.5'),
        nov6: yieldCell('15.1%', 3, 'strike 80.5'),
        nov20: yieldCell('12.2%', 2, 'strike 78', 'report'),
      },
    },
  ],
} satisfies Partial<HeatGridProps>;

/** Graded cells: a yield with its strike, tinted by level, a flag where the span holds a report. */
export const Graded: Story = { args: yieldProps };

export const GradedNarrow: Story = { args: yieldProps, decorators: [narrow] };
