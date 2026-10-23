import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { ShortLabel } from './ShortLabel';

const meta = {
  title: 'Components/ShortLabel',
  component: ShortLabel,
  args: { children: 'Data: 22 Oct, complete', short: 'Data: complete' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a label is text; its owner shows loading',
        Empty: 'a label always has text',
        Error: 'a label is text; its owner shows errors',
      },
    },
  },
} satisfies Meta<typeof ShortLabel>;

export default meta;
type Story = StoryObj<typeof meta>;

/** In a container of 720 px or more the full wording shows. */
export const Default: Story = {};

/** In a phone-wide container the short wording replaces it. */
export const Narrow: Story = { decorators: [narrow] };
