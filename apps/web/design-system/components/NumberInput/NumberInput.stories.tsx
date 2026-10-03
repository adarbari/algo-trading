import type { Meta, StoryObj } from '@storybook/react-vite';

import { Grid } from '../../primitives/Grid';
import { Field } from '../Field';
import { NumberInput } from './NumberInput';

const meta = {
  title: 'Components/NumberInput',
  component: NumberInput,
  args: { 'aria-label': 'IV30 floor', defaultValue: 50, suffix: '%', min: 0, max: 300 },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a number box holds what the user types; loading belongs to the form',
      },
    },
  },
} satisfies Meta<typeof NumberInput>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Units: Story = {
  render: () => (
    <Grid columns={2} gap={2}>
      <Field label="IV − HV">
        <NumberInput defaultValue={10} suffix="pts" step={0.5} />
      </Field>
      <Field label="IV ÷ HV">
        <NumberInput defaultValue={1.25} suffix="×" step={0.05} />
      </Field>
      <Field label="Close above">
        <NumberInput defaultValue={5} prefix="$" step={0.5} precision={2} />
      </Field>
      <Field label="Earnings at least">
        <NumberInput defaultValue={14} suffix="sessions" min={0} />
      </Field>
    </Grid>
  ),
};

export const Empty: Story = { args: { defaultValue: null, placeholder: 'Any' } };

export const Error: Story = {
  render: () => (
    <Field label="Weight" error="Weights add up to 110; reduce one by 10" hint="0 to 100">
      <NumberInput defaultValue={40} min={0} max={100} />
    </Field>
  ),
};

/** Small, right-aligned, as threshold cells in the criteria table. */
export const Dense: Story = {
  render: () => (
    <Grid columns={3} gap={1}>
      <NumberInput aria-label="Threshold 1" size="sm" defaultValue={50} suffix="%" />
      <NumberInput aria-label="Threshold 2" size="sm" defaultValue={10} />
      <NumberInput aria-label="Threshold 3" size="sm" defaultValue={1.25} step={0.05} />
    </Grid>
  ),
};

export const Disabled: Story = { args: { disabled: true } };
