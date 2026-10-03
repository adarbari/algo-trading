import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../Stack';
import { Text } from './Text';

/**
 * Catalogue entry for Text. Every component exports the canonical states (Default, Loading,
 * Empty, Error, Dense) or names the ones that do not apply, with the reason
 * (`parameters.states.notApplicable`; checked by `npm run ds:check`).
 */
const meta = {
  title: 'Primitives/Text',
  component: Text,
  args: { children: 'SPY 30-day IV rank' },
  parameters: {
    states: {
      notApplicable: {
        Loading:
          'Text renders content it is given; loading placeholders are the Skeleton component',
        Empty: 'an empty Text renders nothing; empty data is the EmptyState component',
      },
    },
  },
} satisfies Meta<typeof Text>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Variants: Story = {
  render: () => (
    <Stack gap={2}>
      <Text variant="title">Title: screener results</Text>
      <Text variant="heading">Heading: contract detail</Text>
      <Text variant="body">
        Body: the nightly run finished at 06:12 UTC with 4 812 instruments.
      </Text>
      <Text variant="label">Label: expiry</Text>
      <Text variant="caption">Caption: delayed 15 minutes</Text>
    </Stack>
  ),
};

export const Tones: Story = {
  render: () => (
    <Stack gap={1}>
      <Text tone="default">default</Text>
      <Text tone="muted">muted</Text>
      <Text tone="accent">accent</Text>
      <Text tone="positive">positive</Text>
      <Text tone="negative">negative</Text>
      <Text tone="warning">warning</Text>
      <Text tone="up">+1.24%</Text>
      <Text tone="down">-0.87%</Text>
    </Stack>
  ),
};

export const Error: Story = {
  args: { tone: 'negative', children: 'Chain for 2026-10-02 failed to load' },
};

export const Dense: Story = {
  render: () => (
    <Stack gap={0}>
      {['1,024.50', '98.07', '12.30', '0.45'].map((value) => (
        <Text key={value} variant="caption" numeric mono>
          {value}
        </Text>
      ))}
    </Stack>
  ),
};

export const Truncated: Story = {
  args: {
    truncate: true,
    children: 'A very long instrument description that cannot fit '.repeat(4),
  },
};
