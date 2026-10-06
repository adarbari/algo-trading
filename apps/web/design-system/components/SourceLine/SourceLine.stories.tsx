import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { SourceLine } from './SourceLine';

const NFCI = {
  label: 'Chicago Fed NFCI',
  cadence: 'weekly',
  url: 'https://www.chicagofed.org/research/data/nfci/current-data',
};

const meta = {
  title: 'Components/SourceLine',
  component: SourceLine,
  args: { sources: [NFCI] },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a source line is static text; the figure it sits under shows the loading state',
        Empty: 'no sources renders nothing, so there is no empty state to show',
        Error: 'a source line holds no data of its own; the figure above it shows a failed load',
      },
    },
  },
} satisfies Meta<typeof SourceLine>;

export default meta;
type Story = StoryObj<typeof meta>;

/** One source with its cadence. */
export const Default: Story = {};

/** Several sources, one cadence missing; wraps on a narrow screen. */
export const SeveralSources: Story = {
  args: {
    sources: [
      NFCI,
      { label: 'FRED T10Y3M', cadence: 'daily', url: 'https://fred.stlouisfed.org/series/T10Y3M' },
      { label: 'BLS unemployment', url: 'https://www.bls.gov/cps/' },
    ],
  },
};

/** Under each of a list of meters. */
export const Dense: Story = {
  render: () => (
    <Stack gap={2}>
      <SourceLine sources={[NFCI]} />
      <SourceLine
        sources={[
          {
            label: 'FRED SAHMREALTIME',
            cadence: 'monthly',
            url: 'https://fred.stlouisfed.org/series/SAHMREALTIME',
          },
        ]}
      />
      <SourceLine
        sources={[
          {
            label: 'FRED BAMLH0A0HYM2',
            cadence: 'daily',
            url: 'https://fred.stlouisfed.org/series/BAMLH0A0HYM2',
          },
        ]}
      />
    </Stack>
  ),
};
