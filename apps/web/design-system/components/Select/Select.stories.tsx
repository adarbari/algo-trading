import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Field } from '../Field';
import { Select } from './Select';

const EXPIRIES = [
  { value: '2026-10-16', label: '16 Oct (14d)' },
  { value: '2026-11-20', label: '20 Nov (49d)' },
  { value: '2026-12-18', label: '18 Dec (77d)' },
  { value: '2027-01-15', label: '15 Jan (105d)', disabled: true },
];

const meta = {
  title: 'Components/Select',
  component: Select,
  args: { options: EXPIRIES, defaultValue: '2026-11-20', 'aria-label': 'Expiry' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a Select holds a short, known list; lists that load are Combobox',
      },
    },
  },
} satisfies Meta<typeof Select>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = {
  render: () => <Select aria-label="Expiry" options={EXPIRIES} placeholder="Choose an expiry" />,
};

export const Grouped: Story = {
  args: {
    'aria-label': 'Sort by',
    defaultValue: 'score',
    options: [
      { value: 'score', label: 'Score', group: 'Ranking' },
      { value: 'priority', label: 'Screener priority', group: 'Ranking' },
      { value: 'iv30', label: 'IV30', group: 'Features' },
      { value: 'iv_hv', label: 'IV ÷ HV', group: 'Features' },
    ],
  },
};

export const Error: Story = {
  render: () => (
    <Field label="Expiry" error="This expiry has no quotes for Fri 2 Oct">
      <Select options={EXPIRIES} defaultValue="2026-10-16" />
    </Field>
  ),
};

export const Disabled: Story = { args: { disabled: true } };

/** The small size in a row of controls. */
export const Dense: Story = {
  render: () => (
    <Stack direction="row" gap={1.5}>
      <Select aria-label="Expiry" size="sm" width="auto" options={EXPIRIES} />
      <Select
        aria-label="Side"
        size="sm"
        width="auto"
        options={[
          { value: 'puts', label: 'Puts' },
          { value: 'calls', label: 'Calls' },
        ]}
      />
    </Stack>
  ),
};
