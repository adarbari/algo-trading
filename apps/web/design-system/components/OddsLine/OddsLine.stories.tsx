import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { narrow } from '../../testing';
import { InfoButton } from '../InfoButton';
import { OddsLine } from './OddsLine';

const READY = {
  hitRate: 0.62,
  baseRate: 0.51,
  sessions: 118,
  lift: 1.22,
  picks: 340,
  runLabel: 'edge-eval run 2026-10-02',
};

const meta = {
  title: 'Components/OddsLine',
  component: OddsLine,
  args: READY,
} satisfies Meta<typeof OddsLine>;

export default meta;
type Story = StoryObj<typeof OddsLine>;

/** The evidence for a pick: hit rate against base rate, lift, sessions, picks and the run. */
export const Default: Story = {};

export const Loading: Story = { render: () => <OddsLine state="loading" /> };

export const Empty: Story = { render: () => <OddsLine state="empty" /> };

export const Error: Story = { render: () => <OddsLine state="error" /> };

/** Read outside the frozen period: labelled EXPLORATORY. */
export const Exploratory: Story = { render: () => <OddsLine {...READY} exploratory /> };

/** The required figures only, with the Guide button beside them. */
export const Minimal: Story = {
  render: () => (
    <OddsLine
      hitRate={0.62}
      baseRate={0.51}
      sessions={118}
      info={<InfoButton label="What is the odds line?" />}
    />
  ),
};

/** One per row of a list. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      <OddsLine {...READY} />
      <OddsLine {...READY} hitRate={0.58} baseRate={0.55} sessions={64} lift={1.05} />
      <OddsLine {...READY} exploratory />
    </Stack>
  ),
};

/** In a phone-width container each part takes its own row. */
export const Narrow: Story = { decorators: [narrow], render: () => <OddsLine {...READY} /> };
