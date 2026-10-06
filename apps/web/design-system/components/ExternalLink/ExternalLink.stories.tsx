import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { ExternalLink } from './ExternalLink';

const meta = {
  title: 'Components/ExternalLink',
  component: ExternalLink,
  args: { href: 'https://fred.stlouisfed.org/series/NFCI', children: 'Chicago Fed NFCI' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a link renders the title it is given; its list shows the loading state',
        Empty: 'a link without a title or address is not rendered; the list shows the empty state',
        Error: 'a link holds no data of its own; its list shows a failed load',
      },
    },
  },
} satisfies Meta<typeof ExternalLink>;

export default meta;
type Story = StoryObj<typeof meta>;

/** One reference, at the body size. */
export const Default: Story = {};

/** A reading list at the small size, one link per line. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      <ExternalLink size="sm" href="https://fred.stlouisfed.org/series/T10Y3M">
        FRED: 10-year minus 3-month Treasury spread
      </ExternalLink>
      <ExternalLink size="sm" href="https://www.chicagofed.org/research/data/nfci/current-data">
        Chicago Fed National Financial Conditions Index
      </ExternalLink>
      <ExternalLink size="sm" href="https://fred.stlouisfed.org/series/SAHMREALTIME">
        Sahm rule recession indicator
      </ExternalLink>
    </Stack>
  ),
};
