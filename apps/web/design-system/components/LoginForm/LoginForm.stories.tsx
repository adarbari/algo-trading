import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn, userEvent, within } from 'storybook/test';

import { LoginForm } from './LoginForm';

const meta = {
  title: 'Components/LoginForm',
  component: LoginForm,
  args: { onSubmit: fn() },
  parameters: {
    states: {
      notApplicable: {
        Empty: 'the empty form is the Default story: nothing is stored until it is submitted',
        Dense: 'a single sign-in card has no dense layout; the density tokens already size it',
      },
    },
  },
} satisfies Meta<typeof LoginForm>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The empty form: both fields blank, ready to submit. */
export const Default: Story = {};

/** Both fields typed in (the password shows as dots). */
export const Filled: Story = {
  args: { defaultEmail: 'trader@example.com' },
  play: async ({ canvasElement }) => {
    await userEvent.type(within(canvasElement).getByLabelText(/Password/), 'correct horse');
  },
};

/** The request is running: spinner on the button, fields locked, resubmits ignored. */
export const Loading: Story = { args: { defaultEmail: 'trader@example.com', pending: true } };

/** The attempt failed: one alert above the fields, both marked invalid. */
export const Error: Story = {
  args: { defaultEmail: 'trader@example.com', error: 'Wrong email or password.' },
};

/** A custom title (a second form on the same page, an invitation link). */
export const CustomTitle: Story = { args: { title: 'Sign in to accept your invitation' } };
