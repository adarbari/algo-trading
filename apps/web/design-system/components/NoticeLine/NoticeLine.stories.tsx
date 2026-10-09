import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Banner } from '../Banner';
import { NoticeLine } from './NoticeLine';

const meta = {
  title: 'Components/NoticeLine',
  component: NoticeLine,
  args: {
    label: '6 unavailable',
    summary: 'The IBKR IV table has no rows for 2026-10-07',
    children: (
      <Banner tone="warning" title="Not available: system error">
        IV rank, IV30, IV percentile, HV20, Skew, Term slope
      </Banner>
    ),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a notice reports a known condition; loading is Skeleton',
        Empty: 'a notice exists only when there is something to say',
        Dense: 'one line at every density; the density tokens size it',
      },
    },
  },
} satisfies Meta<typeof NoticeLine>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Expanded: Story = { args: { defaultOpen: true } };

/** The negative tone, for a failure rather than a gap. */
export const Error: Story = { args: { tone: 'negative', label: 'Run failed' } };

export const LongSummary: Story = {
  args: {
    summary:
      'The IBKR IV table has no rows for 2026-10-07 because the gateway was unreachable during the nightly run',
  },
};

export const Narrow: Story = { decorators: [narrow] };
