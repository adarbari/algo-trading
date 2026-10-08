import type { Meta, StoryObj } from '@storybook/react-vite';

import { Heading } from '../../primitives/Heading';
import { Mono } from '../../primitives/Mono';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { narrow } from '../../testing';
import { NavTabs } from '../NavTabs';
import { Panel } from '../Panel';
import { WorkspaceSwitch } from '../WorkspaceSwitch';
import { TopBar } from '../TopBar';
import { AppShell } from './AppShell';

const topBar = (
  <TopBar
    brand={<Mono weight="medium">algotrade</Mono>}
    workspace={
      <WorkspaceSwitch
        workspaces={[
          { value: 'trader', label: 'Trader' },
          { value: 'admin', label: 'Admin' },
        ]}
        value="trader"
        onValueChange={() => undefined}
      />
    }
    nav={
      <NavTabs
        aria-label="Trader sections"
        activeHref="/ideas"
        items={[
          { href: '/ideas', label: 'Ideas' },
          { href: '/screeners', label: 'Screeners' },
          { href: '/explore', label: 'Explore' },
          { href: '/backtests', label: 'Backtests' },
        ]}
      />
    }
    end={<Text tone="muted">As of Fri 2 Oct 2026</Text>}
  />
);

const meta = {
  title: 'Components/AppShell',
  component: AppShell,
  args: {
    topBar,
    children: (
      <>
        <Stack direction="row" gap={3} align="baseline" wrap>
          <Heading level={1}>Ideas for Mon 5 Oct</Heading>
          <Text tone="muted">from Fri 2 Oct close</Text>
        </Stack>
        <Panel title="Your screeners" state="empty" emptyMessage="No screeners yet." />
      </>
    ),
  },
  parameters: {
    layout: 'fullscreen',
    states: {
      notApplicable: {
        Loading: 'the shell is static chrome; the page inside shows loading (Panel state)',
        Error: 'the shell is static chrome; the page inside shows errors (Panel state)',
      },
    },
  },
} satisfies Meta<typeof AppShell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** No page content yet. */
export const Empty: Story = { args: { children: <Heading level={1}>Backtests</Heading> } };

/** Full-width layout for split views. */
export const Full: Story = {
  args: {
    layout: 'full',
    children: <Panel title="Tickers">Edge-to-edge content</Panel>,
  },
};

/** Phone width (a 320 px frame): the top bar wraps and page padding tightens. */
export const Dense: Story = {
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 'var(--size-sidebar)' }}>
        <Story />
      </div>
    ),
  ],
};

/** A phone-width container (375 px): the top bar wraps to two rows and the page padding tightens. */
export const Narrow: Story = { decorators: [narrow] };
