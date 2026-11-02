import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { ProseList } from './ProseList';

const meta = {
  title: 'Components/ProseList',
  component: ProseList,
  args: {
    items: [
      {
        id: 'small',
        lead: 'It is small and spread out.',
        body: 'Each signal pays a few percent over weeks across hundreds of names.',
      },
      {
        id: 'crashes',
        lead: 'It crashes sometimes.',
        body: 'Momentum strategies lose badly when markets rebound sharply.',
      },
      { id: 'plain', body: 'An item without a lead-in is plain running text.' },
    ],
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a list of sentences is static page content',
        Empty: 'an empty list renders nothing; the section around it is left out',
        Error: 'a list holds no data of its own',
      },
    },
  },
} satisfies Meta<typeof ProseList>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Numbered: a fixed order the reader follows. */
export const Ordered: Story = { args: { ordered: true } };

/** A checklist ("Before you act"): an empty box before each line. */
export const Checklist: Story = { args: { marker: 'box' } };

/** Long items wrap inside a phone-width container. */
export const Dense: Story = {
  args: {
    items: Array.from({ length: 6 }, (_, i) => ({
      id: `i${i}`,
      lead: `Point ${i + 1}.`,
      body: 'A longer sentence that wraps over several lines in a narrow container without clipping.',
    })),
  },
};

export const Narrow: Story = { ...Dense, decorators: [narrow] };
