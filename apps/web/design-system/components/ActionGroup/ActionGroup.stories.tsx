import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { ActionGroup } from './ActionGroup';

const noop = () => undefined;

const meta = {
  title: 'Components/ActionGroup',
  component: ActionGroup,
  args: {
    actions: [
      { id: 'run', label: 'Run again', icon: 'refresh', onClick: noop, variant: 'primary' },
      { id: 'columns', label: 'Columns', icon: 'columns', onClick: noop },
      { id: 'filter', label: 'Filter', icon: 'filter', onClick: noop, variant: 'ghost' },
    ],
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'ActionGroup only lays out the actions it is given',
        Empty: 'a page with no actions renders no ActionGroup',
        Error: 'ActionGroup cannot fail; an action reports its own error',
      },
    },
  },
} satisfies Meta<typeof ActionGroup>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Wide: a Button per action. */
export const Default: Story = {};

/** Two actions at the `md` size. */
export const Dense: Story = {
  args: {
    size: 'md',
    actions: [
      { id: 'run', label: 'Run again', icon: 'refresh', onClick: noop },
      { id: 'columns', label: 'Columns', icon: 'columns', onClick: noop },
    ],
  },
};

/** A phone (375 px): an icon button per action, the label in its tooltip. */
export const Narrow: Story = { decorators: [narrow] };
