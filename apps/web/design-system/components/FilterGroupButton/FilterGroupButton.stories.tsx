import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { OptionList } from '../OptionList';
import { FilterGroupButton } from './FilterGroupButton';

const body = (
  <OptionList
    label="Decision"
    value={null}
    values={['QUALIFIED']}
    onSelect={() => undefined}
    items={[
      { id: 'QUALIFIED', title: 'Qualified', count: 41 },
      { id: 'WATCH', title: 'Watch', count: 12 },
    ]}
  />
);

const meta = {
  title: 'Components/FilterGroupButton',
  component: FilterGroupButton,
  args: { label: 'Setup', children: body },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the button shows no data; its body shows its own loading',
        Empty: 'a group with no controls is not rendered',
        Error: 'the button cannot fail',
        Dense: 'the button follows the density tokens',
      },
    },
  },
} satisfies Meta<typeof FilterGroupButton>;

export default meta;
type Story = StoryObj<typeof meta>;

/** No filter in the group. */
export const Default: Story = {};

/** The group holds two filters: accent border and a count badge. */
export const Active: Story = { args: { activeCount: 2 } };

/** The popover open. */
export const Open: Story = { args: { activeCount: 1, defaultOpen: true } };

/** A phone (375 px): the popover stays inside the container's width. */
export const Narrow: Story = { decorators: [narrow], args: { activeCount: 1, defaultOpen: true } };
