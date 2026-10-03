import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { SearchInput } from './SearchInput';

const meta = {
  title: 'Components/SearchInput',
  component: SearchInput,
  args: { placeholder: 'Ticker, name or sector…', 'aria-label': 'Filter tickers' },
  parameters: {
    states: {
      notApplicable: {
        Empty: 'the default story is the empty search box with its placeholder',
      },
    },
  },
} satisfies Meta<typeof SearchInput>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithQuery: Story = { args: { defaultValue: 'semis' } };

export const Loading: Story = { args: { defaultValue: 'NVD', loading: true } };

export const Error: Story = {
  render: () => (
    <Stack gap={1}>
      <SearchInput aria-label="Search tickers" defaultValue="ZZZZ" />
      <Text size="sm" tone="negative">
        Search is unavailable: the universe snapshot did not load.
      </Text>
    </Stack>
  ),
};

/** The top bar's fixed width, small size. */
export const Dense: Story = {
  args: { width: 'fixed', size: 'sm', placeholder: 'Search a ticker…' },
};

export const Disabled: Story = { args: { disabled: true } };
