import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { CauseChain, type CauseLink } from './CauseChain';

const FULL: CauseLink[] = [
  { level: 'SOURCE', subject: 'ibkr', status: 'FAILED', message: 'IB Gateway unreachable' },
  {
    level: 'STEP',
    subject: 'ibkr-iv',
    status: 'FAILED',
    message: 'Connection refused (port 4001)',
  },
  { level: 'TABLE', subject: 'rollups/instrument/ibkr_iv@v1', message: 'No rows for 2026-10-07' },
  { level: 'FEATURE', subject: 'iv_rank, iv_percentile, iv_rank_source' },
  { level: 'RUN', subject: 'vrp_scanner 2026-10-07', status: 'PARTIAL' },
];

const meta = {
  title: 'Components/CauseChain',
  component: CauseChain,
  args: { links: FULL },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a chain is drawn from a cause already fetched; the note around it shows loading',
        Empty: 'no links renders nothing; the note around it says what to show without a cause',
      },
    },
  },
} satisfies Meta<typeof CauseChain>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The full chain from the failed source to the affected run. */
export const Default: Story = {};

export const SingleLink: Story = {
  args: {
    links: [{ level: 'TABLE', subject: 'rollups/instrument/ibkr_iv@v1', status: 'MISSING' }],
  },
};

/** Succeeded, partial, failed and unrecognised states side by side. */
export const Statuses: Story = {
  args: {
    links: [
      { level: 'SOURCE', subject: 'cboe', status: 'SUCCEEDED' },
      { level: 'STEP', subject: 'option-chains', status: 'PARTIAL', message: '12% stale chains' },
      { level: 'TABLE', subject: 'options/chains@v1', status: 'FAILED' },
      { level: 'RUN', subject: 'run-0192', status: 'QUEUED' },
    ],
  },
};

export const Error: Story = {
  args: {
    links: [
      { level: 'STEP', subject: 'ibkr-iv', status: 'FAILED', message: 'Timed out after 30 s' },
    ],
  },
};

/** Long unbroken subjects and messages wrap instead of widening the page. */
export const LongSubjects: Story = {
  args: {
    links: [
      {
        level: 'TABLE',
        subject: 'rollups/instrument/very_long_feature_group_name_with_no_breaks_at_all@v12',
        status: 'MISSING',
        message:
          'No rows for the session because the upstream step failed and nothing was published after it ran',
      },
      {
        level: 'FEATURE',
        subject:
          'feature_one_with_a_long_name, feature_two_with_a_long_name, feature_three_with_a_long_name',
      },
    ],
  },
};

export const Dense: Story = { args: { links: FULL.slice(0, 3) } };

export const Narrow: Story = { decorators: [narrow] };
