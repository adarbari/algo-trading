import type { Meta, StoryObj } from '@storybook/react-vite';

import { Heading } from '../Heading';
import { Stack } from '../Stack';
import { Surface } from '../Surface';
import { Text } from '../Text';
import { Box } from './Box';

const meta = {
  title: 'Primitives/Box',
  component: Box,
  args: {
    padding: 4,
    children: <Text>Content with 16 px padding on every side.</Text>,
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'Box is layout only; loading is shown by the components it holds',
        Error: 'Box is layout only; errors are shown by the components it holds',
      },
    },
  },
} satisfies Meta<typeof Box>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const PaddingXY: Story = {
  render: () => (
    <Surface padding={0}>
      <Box paddingX={4} paddingY={2.5}>
        <Text>Panel header padding: 16 px inline, 10 px block.</Text>
      </Box>
    </Surface>
  ),
};

export const Landmarks: Story = {
  render: () => (
    <Stack gap={0}>
      <Box as="header" paddingX={5} paddingY={2.5}>
        <Text weight="medium">header</Text>
      </Box>
      <Box as="main" width="page" paddingX={6} paddingY={5}>
        <Heading level={1}>main, centred up to the page width</Heading>
      </Box>
      <Box as="footer" paddingX={5} paddingY={2}>
        <Text size="sm" tone="muted">
          footer
        </Text>
      </Box>
    </Stack>
  ),
};

export const Empty: Story = { args: { children: undefined } };

export const Dense: Story = {
  args: { padding: 1, children: <Text size="md">4 px padding for dense cells.</Text> },
};
