import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { WorkspaceSwitch } from './WorkspaceSwitch';

const WORKSPACES = [
  { value: 'trader', label: 'Trader' },
  { value: 'admin', label: 'Admin' },
];

const meta = {
  title: 'Components/WorkspaceSwitch',
  component: WorkspaceSwitch,
  args: { workspaces: WORKSPACES, value: 'trader', onValueChange: () => undefined },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'workspaces are static app configuration; nothing loads',
        Empty: 'there is always at least the default workspace (the switch is hidden with one)',
        Error: 'choosing a workspace cannot fail; a refused workspace is never offered',
        Dense: 'the switch has one size, set by the top bar',
      },
    },
  },
} satisfies Meta<typeof WorkspaceSwitch>;

export default meta;
type Story = StoryObj<typeof meta>;

function Interactive() {
  const [value, setValue] = useState('trader');
  return <WorkspaceSwitch workspaces={WORKSPACES} value={value} onValueChange={setValue} />;
}

export const Default: Story = { render: () => <Interactive /> };

export const Admin: Story = { args: { value: 'admin' } };
