import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Text } from '../../primitives/Text';
import { LazySection } from './LazySection';

const meta = {
  title: 'Components/LazySection',
  component: LazySection,
  args: { label: 'Evidence curve', minBlockSize: 'md', children: <Text>The section.</Text> },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'The placeholder is the loading state: the Placeholder story shows it',
        Empty: 'LazySection holds no data; its children own their empty state',
        Error: 'LazySection holds no data; its children own their error state',
      },
    },
  },
} satisfies Meta<typeof LazySection>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Not yet near the viewport: the Skeleton holds the place (a rootMargin far inside the viewport
 * keeps it from ever intersecting, so the story stays on the placeholder).
 */
export const Placeholder: Story = { args: { rootMargin: '-10000px' } };

/** In view (as in a test or an old browser): the children render at once. */
export const Default: Story = { render: (args) => <LazySection {...args} /> };

/** The tallest reservation, on a phone (placeholder). */
export const Narrow: Story = {
  args: { minBlockSize: 'xl', rootMargin: '-10000px' },
  decorators: [narrow],
};

/** The smallest reservation: a short card. */
export const Dense: Story = { args: { minBlockSize: 'sm' } };
