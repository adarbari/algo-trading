import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Mono } from '../../primitives/Mono';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { AccountMenu } from '../AccountMenu';
import { NavTabs } from '../NavTabs';
import { SearchInput } from '../SearchInput';
import { StatusBadge } from '../StatusBadge';
import { TextLink } from '../TextLink';
import { WorkspaceSwitch } from '../WorkspaceSwitch';
import { TopBar } from './TopBar';

const WORKSPACES = [
  { value: 'trader', label: 'Trader' },
  { value: 'admin', label: 'Admin' },
];
const TRADER = [
  { href: '/ideas', label: 'Ideas' },
  { href: '/screeners', label: 'Screeners' },
  { href: '/explore', label: 'Explore' },
  { href: '/backtests', label: 'Backtests' },
];

const brand = <Mono weight="medium">algotrade</Mono>;

const meta = {
  title: 'Components/TopBar',
  component: TopBar,
  args: {
    brand,
    nav: <NavTabs items={TRADER} activeHref="/ideas" aria-label="Trader sections" />,
    end: <SearchInput width="fixed" placeholder="Search a ticker…" aria-label="Search tickers" />,
  },
  parameters: {
    layout: 'fullscreen',
    states: {
      notApplicable: {
        Loading: 'the bar is static chrome; its slots show their own loading states',
        Error: 'the bar is static chrome; errors belong to the page or a slot',
      },
    },
  },
} satisfies Meta<typeof TopBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Admin workspace with a status note in the end slot. */
export const AdminWithNote: Story = {
  args: {
    nav: (
      <NavTabs
        aria-label="Admin sections"
        activeHref="/admin/ingestion"
        items={[
          { href: '/admin/ingestion', label: 'Ingestion' },
          { href: '/admin/screener-runs', label: 'Screener runs' },
          { href: '/admin/users', label: 'Users & configs' },
        ]}
      />
    ),
    end: <Text tone="muted">Latest session ingested: Fri 2 Oct</Text>,
  },
};

/** The Guide link in the utility slot, before the end slot (both workspaces show it). */
export const WithUtilityLink: Story = {
  args: {
    utility: (
      <TextLink href="/guide" icon="book" keys={['?']} current>
        Guide
      </TextLink>
    ),
    end: <Text tone="muted">Session 2026-10-06</Text>,
  },
};

/** Brand only (sign-in, error pages). */
export const Empty: Story = { args: { nav: undefined, end: undefined } };

/** A 320 px frame, set by the page rather than the container query's frame. */
export const Dense: Story = {
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 'var(--size-sidebar)' }}>
        <Story />
      </div>
    ),
  ],
};

/** The app's slots: the Guide link; the regime chip and the account menu (the workspace switch inside). */
const APP_SLOTS = {
  utility: (
    <TextLink href="/guide" icon="book" keys={['?']}>
      Guide
    </TextLink>
  ),
  end: (
    <Stack direction="row" gap={2} align="center">
      <StatusBadge tone="positive">NORMAL</StatusBadge>
      <AccountMenu name="Abhinav" onSignOut={() => undefined}>
        <Stack gap={1}>
          <Text size="xs" tone="muted">
            Workspace
          </Text>
          <WorkspaceSwitch workspaces={WORKSPACES} value="trader" onValueChange={() => undefined} />
        </Stack>
      </AccountMenu>
    </Stack>
  ),
};

/** The app's bar: brand, nav, the Guide, the regime chip and the account menu. */
export const App: Story = { args: APP_SLOTS };

/**
 * A 375 px phone: brand, Guide and the end slot (one line, scrolling sideways) on the first
 * row, the nav on the second; the workspace switch waits in the account menu.
 */
export const Narrow: Story = { args: APP_SLOTS, decorators: [narrow] };
