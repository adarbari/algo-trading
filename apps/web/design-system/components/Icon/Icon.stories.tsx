import type { Meta, StoryObj } from '@storybook/react-vite';

import { Grid } from '../../primitives/Grid';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Icon, ICON_NAMES } from './Icon';

const meta = {
  title: 'Components/Icon',
  component: Icon,
  args: { name: 'search' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'an icon is static; the loading indicator itself is the Spinner story',
        Empty: 'an icon always draws one glyph; there is no empty icon',
      },
    },
  },
} satisfies Meta<typeof Icon>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** The whole set at the default size, with names. */
export const All: Story = {
  render: () => (
    <Grid columns={4} gap={3}>
      {ICON_NAMES.map((name) => (
        <Stack key={name} direction="row" gap={2} align="center">
          <Icon name={name} />
          <Text size="sm" tone="secondary" mono>
            {name}
          </Text>
        </Stack>
      ))}
    </Grid>
  ),
};

export const Sizes: Story = {
  render: () => (
    <Stack direction="row" gap={4} align="center">
      <Icon name="filter" size="sm" />
      <Icon name="filter" size="md" />
      <Icon name="filter" size="lg" />
    </Stack>
  ),
};

export const Tones: Story = {
  render: () => (
    <Stack direction="row" gap={3} align="center">
      <Icon name="info" tone="muted" label="Muted" />
      <Icon name="info" tone="secondary" label="Secondary" />
      <Icon name="info" tone="accent" label="Accent" />
      <Icon name="check" tone="positive" label="Passed" />
      <Icon name="alert" tone="warning" label="Warning" />
      <Icon name="alert" tone="negative" label="Failed" />
      <Icon name="info" tone="info" label="Note" />
    </Stack>
  ),
};

export const Spinner: Story = { args: { name: 'spinner', spin: true, label: 'Loading' } };

export const Error: Story = {
  render: () => (
    <Stack direction="row" gap={1.5} align="center">
      <Icon name="alert" tone="negative" />
      <Text tone="negative">Chain fetch failed</Text>
    </Stack>
  ),
};

/** Small icons inline with dense text. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      {(['check', 'alert', 'close'] as const).map((name) => (
        <Stack key={name} direction="row" gap={1} align="center">
          <Icon name={name} size="sm" tone="muted" />
          <Text size="sm">{name}</Text>
        </Stack>
      ))}
    </Stack>
  ),
};
