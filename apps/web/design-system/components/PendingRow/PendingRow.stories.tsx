import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Button } from '../Button';
import { PendingRow } from './PendingRow';

const meta = {
  title: 'Components/PendingRow',
  component: PendingRow,
  args: {
    label: 'Waiting on formula',
    name: 'feature.draft_near_52w_high',
    summary: '>= -0.05',
    actions: (
      <>
        <Button variant="primary" size="sm">
          Review and add
        </Button>
        <Button variant="ghost" size="sm">
          Skip
        </Button>
      </>
    ),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading:
          'a pending row is a placeholder for a decision; the owner shows the formula’s own loading',
        Empty: 'a pending row exists only when there is something pending',
        Error: 'a failed save shows in the review dialog, not in the row',
        Dense: 'it is one row; there is no density variant',
      },
    },
  },
} satisfies Meta<typeof PendingRow>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The Describe it example: a criterion on a formula the trader has not accepted. */
export const Default: Story = {};

/** Without a summary or actions (the status and the name only). */
export const Bare: Story = { args: { summary: undefined, actions: undefined } };

/** A phone: the actions go under the name and take the full width. */
export const Narrow: Story = { decorators: [narrow] };
