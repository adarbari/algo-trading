import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Checkbox } from './Checkbox';

const meta = {
  title: 'Components/Checkbox',
  component: Checkbox,
  args: { label: 'Include leveraged ETFs' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a checkbox is a local choice; nothing loads',
        Empty: 'a checkbox always has a label; unchecked is the Default story',
      },
    },
  },
} satisfies Meta<typeof Checkbox>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const States: Story = {
  render: () => (
    <Stack gap={2}>
      <Checkbox label="Unchecked" />
      <Checkbox label="Checked" defaultChecked />
      <Checkbox label="Some selected" indeterminate />
      <Checkbox label="Disabled" disabled />
      <Checkbox label="Disabled and checked" disabled defaultChecked />
    </Stack>
  ),
};

export const WithDescription: Story = {
  args: {
    label: 'Flag earnings risk',
    description: 'Mark names reporting in the next 14 sessions as EVENT_RISK',
    defaultChecked: true,
  },
};

export const Error: Story = {
  render: () => (
    <Stack gap={1}>
      <Checkbox label="I understand this screen is for research only" invalid />
      <Text size="sm" tone="negative">
        Confirm to continue.
      </Text>
    </Stack>
  ),
};

/** Row-selection boxes with screen-reader-only labels, as in the ticker table. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      {['AAPL', 'MSFT', 'NVDA', 'SPY'].map((sym, i) => (
        <Stack key={sym} direction="row" gap={2} align="center">
          <Checkbox label={`Select ${sym}`} hideLabel defaultChecked={i < 3} />
          <Text mono>{sym}</Text>
        </Stack>
      ))}
    </Stack>
  ),
};
