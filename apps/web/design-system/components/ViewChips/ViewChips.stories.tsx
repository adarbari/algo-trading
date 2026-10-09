import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { narrow } from '../../testing';
import { ViewChips } from './ViewChips';

const VIEWS = [
  { value: 'top', label: 'Top today' },
  { value: 'conviction', label: 'High conviction' },
  { value: 'no-earnings', label: 'No earnings within 10 days' },
];

function Held({ views = VIEWS }: { views?: typeof VIEWS }) {
  const [value, setValue] = useState(views[0]?.value ?? '');
  return <ViewChips views={views} value={value} onValueChange={setValue} />;
}

const meta = {
  title: 'Components/ViewChips',
  component: ViewChips,
  args: { views: VIEWS, value: 'top', onValueChange: () => undefined },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the views are given; nothing loads here',
        Error: 'the views are given; nothing can fail here',
      },
    },
  },
} satisfies Meta<typeof ViewChips>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { render: () => <Held /> };

/** No saved views: nothing is drawn. */
export const Empty: Story = { render: () => <Held views={[]} /> };

/** Many views wrap onto lines. */
export const Dense: Story = {
  render: () => (
    <Held
      views={[
        ...VIEWS,
        { value: 'a', label: 'Mean reversion only' },
        { value: 'b', label: 'My watchlist' },
        { value: 'c', label: 'Large caps' },
      ]}
    />
  ),
};

/** A 375 px phone frame: the row wraps, never scrolls the page sideways. */
export const Narrow: Story = { ...Dense, decorators: [narrow] };
