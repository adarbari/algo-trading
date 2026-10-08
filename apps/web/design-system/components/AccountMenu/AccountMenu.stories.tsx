import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { WorkspaceSwitch } from '../WorkspaceSwitch';
import { AccountMenu } from './AccountMenu';

const WORKSPACES = [
  { value: 'trader', label: 'Trader' },
  { value: 'admin', label: 'Admin' },
];

const meta = {
  title: 'Components/AccountMenu',
  component: AccountMenu,
  args: {
    name: 'Bo',
    onSignOut: () => undefined,
    children: (
      <Stack gap={1}>
        <Text size="xs" tone="muted">
          Workspace
        </Text>
        <WorkspaceSwitch workspaces={WORKSPACES} value="trader" onValueChange={() => undefined} />
      </Stack>
    ),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the menu lists static choices; the viewer loads before the bar renders it',
        Empty: 'a viewer always has a name; a trader with one workspace sees Sign out alone',
        Error: 'the menu holds controls; errors belong to the page',
      },
    },
  },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: 'Bo' }));
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeVisible());
  },
} satisfies Meta<typeof AccountMenu>;

export default meta;
type Story = StoryObj<typeof meta>;

/** An admin: the workspace switch and Sign out (opened). */
export const Default: Story = {};

/** A trader with the API's auth off: the name alone, no switch, no sign-out. */
export const Dense: Story = {
  render: () => <AccountMenu name="Ann" />,
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: 'Ann' }));
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeVisible());
  },
};
