import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { NavTabs } from './NavTabs';

const TRADER = [
  { href: '/ideas', label: 'Ideas' },
  { href: '/screeners', label: 'Screeners' },
  { href: '/explore', label: 'Explore' },
  { href: '/backtests', label: 'Backtests' },
];

const meta = {
  title: 'Components/NavTabs',
  component: NavTabs,
  args: { items: TRADER, activeHref: '/screeners', 'aria-label': 'Trader sections' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'sections are static app configuration; nothing loads',
        Empty: 'a workspace always has at least one section',
        Error: 'navigation links cannot fail; a missing page is the router not-found page',
      },
    },
  },
} satisfies Meta<typeof NavTabs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Admin: Story = {
  args: {
    'aria-label': 'Admin sections',
    activeHref: '/admin/ingestion',
    items: [
      { href: '/admin/ingestion', label: 'Ingestion' },
      { href: '/admin/screener-runs', label: 'Screener runs' },
      { href: '/admin/users', label: 'Users & configs' },
    ],
  },
};

/** Many sections in one row that scrolls sideways. */
export const Dense: Story = {
  args: {
    activeHref: '/s5',
    items: Array.from({ length: 9 }, (_, i) => ({ href: `/s${i + 1}`, label: `Section ${i + 1}` })),
  },
};

/** A phone frame: the row scrolls and the current section (7th) is scrolled into view. */
export const Narrow: Story = {
  ...Dense,
  args: { ...Dense.args, activeHref: '/s8' },
  decorators: [narrow],
};
