import type { Meta, StoryObj } from '@storybook/react-vite';

import { Box } from '../../primitives/Box';
import { Stack } from '../../primitives/Stack';
import { Surface } from '../../primitives/Surface';
import { Text } from '../../primitives/Text';
import { InfoButton } from './InfoButton';

const HEADERS = ['breakout_magnitude_20d', 'dist_to_high_50d', 'rel_volume', 'atr_ratio_5_20'];

const meta = {
  title: 'Components/InfoButton',
  component: InfoButton,
  args: { label: 'What is rel_volume?' },
  decorators: [
    (Story) => (
      <Box paddingY={10} paddingX={4}>
        <Story />
      </Box>
    ),
  ],
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a button that opens an explanation is ready as soon as it is drawn',
        Empty: 'an info button always has a label; no explanation means no button',
        Dense: 'it is already the compact form; InTableHeader shows it inline in a header row',
        Error: 'a failed explanation is shown by the HelpDrawer content, not by the button',
      },
    },
  },
} satisfies Meta<typeof InfoButton>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Quiet beside its subject; hover and focus lift it. */
export const Default: Story = {};

/** A one-sentence tooltip on hover and keyboard focus. */
export const WithSummary: Story = {
  args: {
    summary:
      'The session’s volume over the average of the 20 sessions before it: 1 is normal, 2 is twice normal.',
  },
  render: (args) => (
    <Stack direction="row" gap={1} align="center">
      <Text weight="medium">rel_volume</Text>
      <InfoButton {...args} />
    </Stack>
  ),
};

/** While its drawer is open: pressed style and aria-expanded. */
export const Expanded: Story = { args: { expanded: true } };

/** Inline in table headers: the row height is the text's, not the button's. */
export const InTableHeader: Story = {
  render: () => (
    <Surface border="all">
      <Box paddingX={3} paddingY={2}>
        <Stack direction="row" gap={4} align="center" wrap>
          <Text size="sm" tone="muted" weight="medium">
            Symbol
          </Text>
          {HEADERS.map((name) => (
            <Stack key={name} direction="row" gap={1} align="center">
              <Text size="sm" tone={name === 'rel_volume' ? 'accent' : 'muted'} weight="medium">
                {name}
              </Text>
              <InfoButton
                label={`What is ${name}?`}
                expanded={name === 'rel_volume' ? true : undefined}
              />
            </Stack>
          ))}
          <Text size="sm" tone="muted" weight="medium">
            Decision
          </Text>
        </Stack>
      </Box>
    </Surface>
  ),
};
