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

export const Sizes: Story = {
  render: () => (
    <Stack gap={1}>
      <Text size="xs">xs 11.5: column header, legend</Text>
      <Text size="sm">sm 12: caption, metadata</Text>
      <Text size="md">md 12.5: table cell</Text>
      <Text size="base">base 13: body (default)</Text>
      <Text size="lg">lg 14: emphasis</Text>
      <Text size="xl">xl 16: section lead</Text>
      <Text size="2xl" weight="medium">
        2xl 18: summary figure
      </Text>
      <Text size="3xl" weight="medium">
        3xl 22: hero figure
      </Text>
    </Stack>
  ),
};

export const Weights: Story = {
  render: () => (
    <Stack direction="row" gap={4}>
      <Text weight="regular">Regular 400</Text>
      <Text weight="medium">Medium 500</Text>
      <Text weight="semibold">Semibold 600</Text>
    </Stack>
  ),
};

export const Tones: Story = {
  render: () => (
    <Stack gap={1}>
      <Text tone="default">default: primary text</Text>
      <Text tone="secondary">secondary: inactive nav, legend values</Text>
      <Text tone="muted">muted: captions, units</Text>
      <Text tone="accent">accent: a link</Text>
      <Text tone="positive">positive: 5 checks pass</Text>
      <Text tone="warning">warning: stale chains 12.3%</Text>
      <Text tone="negative">negative: fetch failed</Text>
      <Text tone="info">info: delayed 15 minutes</Text>
      <Text tone="up" numeric>
        +1.24%
      </Text>
      <Text tone="down" numeric>
        -0.87%
      </Text>
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
        <Text key={value} size="md" numeric>
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
