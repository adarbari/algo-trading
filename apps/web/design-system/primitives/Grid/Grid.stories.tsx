import type { Meta, StoryObj } from '@storybook/react-vite';

import { Mono } from '../Mono';
import { Surface } from '../Surface';
import { Text } from '../Text';
import { Grid } from './Grid';

const cell = (label: string) => (
  <Surface key={label} tone="row" border="none" radius="sm" padding={2}>
    <Text size="sm">{label}</Text>
  </Surface>
);

const meta = {
  title: 'Primitives/Grid',
  component: Grid,
  args: { columns: 4, gap: 2, children: ['1', '2', '3', '4', '5', '6', '7', '8'].map(cell) },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'Grid is layout only; loading is shown by the components it holds',
        Error: 'Grid is layout only; errors are shown by the components it holds',
      },
    },
  },
} satisfies Meta<typeof Grid>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const LabelValue: Story = {
  args: {
    columns: 'label-value',
    gap: 1,
    rowGap: 1,
    children: [
      ['Underlying', 'SPY'],
      ['Expiry', '2026-10-16'],
      ['Strike', '575.00'],
    ].flatMap(([k = '', v = '']) => [
      <Text key={k} tone="muted" size="sm">
        {k}
      </Text>,
      <Mono key={v}>{v}</Mono>,
    ]),
  },
};

export const MainAside: Story = {
  args: { columns: 'main-aside', gap: 4, children: ['main (3)', 'aside (2)'].map(cell) },
};

export const Collapsed: Story = {
  args: { columns: 4, collapse: 'lg', children: ['1', '2', '3', '4'].map(cell) },
};

export const Empty: Story = { args: { children: undefined } };

export const Dense: Story = {
  args: { columns: 6, gap: 0.5, children: Array.from({ length: 12 }, (_, i) => cell(`${i + 1}`)) },
};
