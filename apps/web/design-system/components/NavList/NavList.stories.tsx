import type { Meta, StoryObj } from '@storybook/react-vite';

import { NavList } from './NavList';

const meta = {
  title: 'Components/NavList',
  component: NavList,
  args: {
    'aria-label': 'Guide',
    items: [
      { href: '/guide', label: 'Start here' },
      { href: '/guide/fields', label: 'Fields', count: 399, current: true },
      { href: '/guide/situations', label: 'Situations', count: 7 },
    ],
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the list is built from data the page has already loaded',
        Error: 'the page shows its own error instead of an empty rail',
      },
    },
  },
} satisfies Meta<typeof NavList>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** A section with its themes and the open theme's fields (catalogue names in mono). */
export const Nested: Story = {
  args: {
    items: [
      { href: '/guide', label: 'Start here' },
      {
        href: '/guide/fields',
        label: 'Fields',
        count: 399,
        children: [
          { href: '/guide/fields?theme=price-levels', label: 'Price levels', count: 56 },
          {
            href: '/guide/fields?theme=momentum',
            label: 'Momentum and trend',
            count: 54,
            current: true,
            children: [
              { href: '/guide/fields/one_day_move', label: 'one_day_move', mono: true },
              { href: '/guide/fields/rel_volume', label: 'rel_volume', mono: true, current: true },
              { href: '/guide/fields/rsi_14', label: 'rsi_14', mono: true },
            ],
          },
        ],
      },
    ],
  },
};

/** A page's own anchors, small. */
export const Dense: Story = {
  args: {
    'aria-label': 'On this page',
    size: 'sm',
    items: [
      { href: '#reads', label: 'How to read it', current: true },
      { href: '#dist', label: 'Distribution' },
      { href: '#use', label: 'Use it for' },
    ],
  },
};

/** No entries yet: the landmark stays, with nothing in it. */
export const Empty: Story = { args: { items: [] } };
