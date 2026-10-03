import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor } from 'storybook/test';

import { Box } from '../../primitives/Box';
import { Stack } from '../../primitives/Stack';
import { Button } from '../Button';
import { IconButton } from '../IconButton';
import { Kbd } from '../Kbd';
import { Tooltip } from './Tooltip';

const meta = {
  title: 'Components/Tooltip',
  component: Tooltip,
  args: {
    content: 'IV30 ÷ HV30: how rich options are against realised moves',
    children: (props) => (
      <Button {...props} size="sm" variant="ghost">
        IV / HV
      </Button>
    ),
  },
  decorators: [
    (Story) => (
      <Box paddingY={10}>
        <Story />
      </Box>
    ),
  ],
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a tooltip shows static text about its trigger; it never loads',
        Empty: 'a tooltip always has content; no content means no Tooltip',
        Error: 'a tooltip shows static text; errors belong to the control or an ErrorState',
      },
    },
  },
} satisfies Meta<typeof Tooltip>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Shown (as on hover). */
export const Default: Story = { args: { defaultOpen: true } };

/** Keyboard focus shows it at once; Escape hides it. */
export const OnFocus: Story = {
  args: {
    content: (
      <>
        Search tickers <Kbd keys={['/']} size="xs" />
      </>
    ),
    placement: 'bottom',
    children: (props) => <IconButton {...props} icon="search" label="Search" variant="secondary" />,
  },
  play: async () => {
    await userEvent.tab();
    await waitFor(() => expect(document.querySelector('[role="tooltip"]')).toBeVisible());
  },
};

/** Tooltips on a toolbar's icon buttons (closed until hover or focus). */
export const Dense: Story = {
  render: () => (
    <Stack direction="row" gap={1}>
      {(
        [
          ['refresh', 'Re-run preview'],
          ['filter', 'Filter'],
          ['columns', 'Columns'],
        ] as const
      ).map(([icon, label]) => (
        <Tooltip key={icon} content={label}>
          {(props) => <IconButton {...props} icon={icon} label={label} size="sm" />}
        </Tooltip>
      ))}
    </Stack>
  ),
};
