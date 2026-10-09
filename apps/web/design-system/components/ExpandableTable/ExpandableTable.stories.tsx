import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { Mono } from '../../primitives/Mono';
import { Text } from '../../primitives/Text';
import { narrow } from '../../testing';
import { StackedBar } from '../StackedBar';
import { StatusBadge } from '../StatusBadge';
import { ExpandableTable, type ExpandableTableColumn } from './ExpandableTable';

const COLUMNS: ExpandableTableColumn[] = [
  { id: 'name', label: 'Screener', grow: 2, narrow: true },
  { id: 'picks', label: 'Picks today', align: 'end', narrow: true },
  { id: 'decisions', label: 'Decisions' },
  { id: 'record', label: 'Track record', narrow: true },
  { id: 'run', label: 'Last run' },
];

const nameCell = (name: string, kind: string, edge: string) => (
  <>
    <span>
      <Text weight="medium">{name}</Text> <StatusBadge tone="neutral">{kind}</StatusBadge>
    </span>
    <Text size="xs" tone="muted">
      {edge}
    </Text>
  </>
);

const bar = (qualified: number, watch: number) => (
  <StackedBar
    label="Decisions"
    size="sm"
    showLegend={false}
    segments={[
      { id: 'q', label: 'Qualified', value: qualified, tone: 'positive' },
      { id: 'w', label: 'Watch', value: watch, tone: 'accent' },
    ]}
  />
);

const ROWS = [
  {
    id: 'breakout',
    cells: {
      name: nameCell('Breakout with volume', 'Preset', 'Edge: Breakouts persist'),
      picks: <Mono>14</Mono>,
      decisions: bar(14, 6),
      record: <Text size="sm">61% vs 53% base</Text>,
      run: (
        <Text size="sm" tone="muted">
          2026-10-08
        </Text>
      ),
    },
  },
  {
    id: 'oversold',
    cells: {
      name: nameCell('Oversold quality', 'Mine', 'Not part of an edge'),
      picks: <Mono>6</Mono>,
      decisions: bar(6, 3),
      record: (
        <Text size="sm" tone="muted">
          No record yet
        </Text>
      ),
      run: <StatusBadge tone="warning">No run today</StatusBadge>,
    },
  },
];

const meta = {
  title: 'Components/ExpandableTable',
  component: ExpandableTable,
  args: { label: 'Screeners', columns: COLUMNS, rows: [] },
  render: (args, { parameters }) => {
    const [open, setOpen] = useState<string | null>(
      typeof parameters['open'] === 'string' ? parameters['open'] : null,
    );
    return (
      <ExpandableTable
        {...args}
        rows={ROWS.map((r) => ({
          ...r,
          open: open === r.id,
          onOpenChange: (next) => {
            setOpen(next ? r.id : null);
          },
          detail: <Text size="sm">Criteria, today, top hits, track record and actions.</Text>,
        }))}
      />
    );
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a table shows the rows it is given; the detail loads itself once open',
        Empty: 'a list with no rows shows its own empty state',
        Dense: 'one density: the rows are as tall as the density tokens make them',
        Error: 'a table holds no data of its own; the list shows a failed load',
      },
    },
  },
} satisfies Meta<typeof ExpandableTable>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Open: Story = { parameters: { open: 'breakout' } };

/** A phone (375 px): the columns marked `narrow` only, the header following. */
export const Narrow: Story = { decorators: [narrow] };
