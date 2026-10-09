import type { Meta, StoryObj } from '@storybook/react-vite';

import { Box } from '../../primitives/Box';
import { Text } from '../../primitives/Text';
import { narrow } from '../../testing';
import { SectionNav } from './SectionNav';

const ITEMS = [
  { id: 'now', label: 'Now' },
  { id: 'why', label: 'Why' },
  { id: 'history', label: 'History' },
];

const meta = {
  title: 'Components/SectionNav',
  component: SectionNav,
  args: { items: ITEMS, 'aria-label': 'Page sections' },
  render: (args) => (
    <div>
      <SectionNav {...args} />
      {args.items.map((item) => (
        <Box key={item.id} as="section" id={item.id} paddingY={10}>
          <Text>{item.label} section</Text>
        </Box>
      ))}
    </div>
  ),
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the sections are a page layout; nothing loads',
        Empty: 'a page with sections has at least one',
        Error: 'in-page links cannot fail',
        Dense: 'a page has a handful of sections; the row scrolls sideways when they do not fit',
      },
    },
  },
} satisfies Meta<typeof SectionNav>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Three sections; the first is marked until the scroll reaches another. */
export const Default: Story = {};

/** A phone (375 px): the same row. */
export const Narrow: Story = { decorators: [narrow] };
