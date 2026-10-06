import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { LoginForm } from './LoginForm';

async function fill(email: string, password: string) {
  await userEvent.type(screen.getByLabelText(/Email/), email);
  await userEvent.type(screen.getByLabelText(/Password/), password);
}

describe('LoginForm', () => {
  it('labels both fields and titles the form', () => {
    render(<LoginForm onSubmit={vi.fn()} />);
    expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Email/ })).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText(/Password/)).toHaveAttribute('type', 'password');
  });

  it('uses a custom title', () => {
    render(<LoginForm onSubmit={vi.fn()} title="Welcome back" />);
    expect(screen.getByRole('form', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('submits the credentials with the button', async () => {
    const onSubmit = vi.fn();
    render(<LoginForm onSubmit={onSubmit} />);
    await fill(' trader@example.com ', 'secret');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      email: 'trader@example.com',
      password: 'secret',
    });
  });

  it('tells the page when either field is edited', async () => {
    const onEdit = vi.fn();
    render(<LoginForm onSubmit={vi.fn()} onEdit={onEdit} />);
    await userEvent.type(screen.getByLabelText(/Email/), 'a');
    expect(onEdit).toHaveBeenCalledTimes(1);
    await userEvent.type(screen.getByLabelText(/Password/), 'b');
    expect(onEdit).toHaveBeenCalledTimes(2);
  });

  it('submits on Enter from the password field', async () => {
    const onSubmit = vi.fn();
    render(<LoginForm onSubmit={onSubmit} defaultEmail="a@b.co" />);
    await userEvent.type(screen.getByLabelText(/Password/), 'secret{Enter}');
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ email: 'a@b.co', password: 'secret' });
  });

  it('does not submit an empty form', async () => {
    const onSubmit = vi.fn();
    render(<LoginForm onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('shows the error as an alert that describes both invalid fields', () => {
    render(<LoginForm onSubmit={vi.fn()} error="Wrong email or password." />);
    expect(screen.getByRole('alert')).toHaveTextContent('Wrong email or password.');
    for (const field of [screen.getByLabelText(/Email/), screen.getByLabelText(/Password/)]) {
      expect(field).toBeInvalid();
      expect(field).toHaveAccessibleDescription('Wrong email or password.');
    }
  });

  it('has no alert and valid fields without an error', () => {
    render(<LoginForm onSubmit={vi.fn()} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Email/)).not.toHaveAttribute('aria-invalid');
  });

  it('locks the fields and ignores submits while pending', async () => {
    const onSubmit = vi.fn();
    render(<LoginForm onSubmit={onSubmit} defaultEmail="a@b.co" pending />);
    expect(screen.getByLabelText(/Email/)).toBeDisabled();
    expect(screen.getByLabelText(/Password/)).toBeDisabled();
    const button = screen.getByRole('button', { name: 'Sign in' });
    expect(button).toHaveAttribute('aria-busy', 'true');
    await userEvent.click(button);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('has no accessibility violations in any state', async () => {
    const { container, rerender } = render(<LoginForm onSubmit={vi.fn()} />);
    await expectNoA11yViolations(container);
    rerender(<LoginForm onSubmit={vi.fn()} error="Wrong email or password." />);
    await expectNoA11yViolations(container);
    rerender(<LoginForm onSubmit={vi.fn()} pending />);
    await expectNoA11yViolations(container);
  });
});
