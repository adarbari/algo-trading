import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { LinkButton } from './LinkButton';

const meta = {
  title: 'Components/LinkButton',
  component: LinkButton,
  args: { children: '12 picks', onClick: () => undefined },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a link shows the words it is given; the cell around it shows loading',
        Empty: 'a link with no words is not rendered',
        Dense: 'one density: it takes the text size around it',
        Error: 'a link holds no data of its own',
      },
    },
  },
} satisfies Meta<typeof LinkButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** A phone (375 px): the same link inside a narrow container. */
export const Narrow: Story = { decorators: [narrow] };
