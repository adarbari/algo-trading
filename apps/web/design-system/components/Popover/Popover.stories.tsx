import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { Checkbox } from '../Checkbox';
import { Field } from '../Field';
import { NumberInput } from '../NumberInput';
import { Popover } from './Popover';

const open = async ({ canvasElement }: { canvasElement: HTMLElement }) => {
  await userEvent.click(within(canvasElement).getByRole('button'));
  await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeVisible());
};

const meta = {
  title: 'Components/Popover',
  component: Popover,
  args: {
    label: 'Show',
    trigger: (props) => (
      <Button {...props} size="sm" iconEnd="chevron-down">
        Show
      </Button>
    ),
    children: (
      <Stack gap={2}>
        <Checkbox label="Stocks" defaultChecked />
        <Checkbox label="ETFs" defaultChecked />
        <Checkbox label="ADRs" description="American depositary receipts" />
        <Checkbox label="Leveraged ETFs" />
      </Stack>
    ),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a popover is a container; its content shows its own loading state',
        Empty: 'a popover is a container; its content shows its own empty state',
        Error: 'a popover is a container; its content shows its own error state',
      },
    },
  },
} satisfies Meta<typeof Popover>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Closed: the trigger only. */
export const Default: Story = {};

/** Open below its trigger (a click opens it; Escape or a click outside closes it). */
export const Open: Story = { play: open };

/** A small form that keeps focus inside (`trapFocus`). */
export const WithForm: Story = {
  args: {
    label: 'Edit criterion',
    trapFocus: true,
    trigger: (props) => (
      <Button {...props} size="sm">
        IV / HV ≥ 1.10
      </Button>
    ),
    children: (
      <Stack gap={3}>
        <Text size="sm" tone="muted">
          IV30 ÷ HV30, at least
        </Text>
        <Field label="Minimum">
          <NumberInput defaultValue={1.1} step={0.05} min={0} />
        </Field>
        <Stack direction="row" gap={2} justify="end">
          <Button size="sm" variant="ghost">
            Cancel
          </Button>
          <Button size="sm" variant="primary">
            Apply
          </Button>
        </Stack>
      </Stack>
    ),
  },
  play: open,
};

/** A flush list (the DataTable column picker uses `padding="none"`, `width="wide"`). */
export const Dense: Story = {
  args: {
    padding: 'none',
    width: 'wide',
    placement: 'bottom-start',
  },
  play: open,
};
