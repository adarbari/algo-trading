import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { OnboardUserForm } from './OnboardUserForm';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn() } };
});
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

const POST = vi.mocked(api.POST);

beforeEach(() => {
  POST.mockReset();
});

async function fill() {
  await userEvent.type(screen.getByRole('textbox', { name: /User id/ }), 'eva');
  await userEvent.type(screen.getByRole('textbox', { name: /Email/ }), 'eva@example.com');
  await userEvent.type(screen.getByRole('textbox', { name: /Name/ }), 'Eva');
}

const setup = () =>
  render(
    <TestQueryProvider>
      <OnboardUserForm />
    </TestQueryProvider>,
  );

describe('OnboardUserForm', () => {
  it('onboards, then shows the address to add and the Guide entries for the remaining step', async () => {
    POST.mockResolvedValue({
      data: {
        user_id: 'eva',
        role: 'trader',
        pending_provider: true,
        provider_step: { email: 'eva@example.com', instruction: 'supabase_add_user' },
      },
      response: new Response(null, { status: 201 }),
    });
    const { container } = setup();
    expect(screen.getByRole('button', { name: 'Onboard' })).toBeDisabled();
    await fill();
    await userEvent.click(screen.getByRole('button', { name: 'Onboard' }));
    expect(await screen.findByText('eva@example.com')).toBeInTheDocument();
    expect(POST).toHaveBeenCalledWith('/users', {
      body: { user_id: 'eva', email: 'eva@example.com', name: 'Eva' },
    });
    expect(screen.getByText('help user_supabase_step')).toBeInTheDocument();
    expect(screen.getByText('help user_pending_provider')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /User id/ })).toHaveValue('');
    await expectNoA11yViolations(container);
  });

  it.each([
    [400, 'invalid email'],
    [403, 'admin only'],
    [409, 'email already held'],
  ])('shows the server detail on a %s and keeps what was typed', async (status, detail) => {
    POST.mockResolvedValue({ error: { detail }, response: new Response(null, { status }) });
    setup();
    await fill();
    await userEvent.click(screen.getByRole('button', { name: 'Onboard' }));
    expect(await screen.findByText(detail)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /User id/ })).toHaveValue('eva');
    });
  });

  it('refuses an invalid id before sending', async () => {
    setup();
    await userEvent.type(screen.getByRole('textbox', { name: /User id/ }), 'No Good');
    expect(screen.getByText('Use 1-64 of a-z, 0-9, _ and -.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Onboard' })).toBeDisabled();
  });
});
