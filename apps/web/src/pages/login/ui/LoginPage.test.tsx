import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  AuthFailure,
  gql,
  signInWithPassword,
  signOutSession,
  TestQueryProvider,
} from '@/shared/api';

import { LoginPage } from './LoginPage';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn(), signInWithPassword: vi.fn(), signOutSession: vi.fn() };
});

const TRADER = { id: 'ann', name: 'Ann', role: 'trader', workspaces: ['trader'] };

beforeEach(() => {
  vi.mocked(signInWithPassword).mockResolvedValue(undefined);
  vi.mocked(signOutSession).mockResolvedValue(undefined);
});

async function submit(email = 'ann@example.com', password = 'pw') {
  await userEvent.type(screen.getByLabelText(/Email/), email);
  await userEvent.type(screen.getByLabelText(/Password/), password);
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

function setup(notice?: string) {
  const onSignedIn = vi.fn();
  render(
    <TestQueryProvider>
      <LoginPage notice={notice} onSignedIn={onSignedIn} />
    </TestQueryProvider>,
  );
  return onSignedIn;
}

describe('LoginPage', () => {
  it('shows the sign-in form on the page main landmark', () => {
    setup();
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Sign in to algotrade' })).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('signs in and moves on once the API knows the user', async () => {
    vi.mocked(gql).mockResolvedValue({ viewer: TRADER });
    const onSignedIn = setup();
    await submit();
    await waitFor(() => {
      expect(onSignedIn).toHaveBeenCalledTimes(1);
    });
    expect(signInWithPassword).toHaveBeenCalledWith('ann@example.com', 'pw');
  });

  it('explains wrong credentials and clears the message when the user edits', async () => {
    vi.mocked(signInWithPassword).mockRejectedValue(
      new AuthFailure('Invalid login credentials', 'invalid_credentials'),
    );
    const onSignedIn = setup();
    await submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong email or password.');
    expect(onSignedIn).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/Password/), 'x');
    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  it('tells a user the registry does not know to ask an admin', async () => {
    vi.mocked(gql).mockRejectedValue(new ApiError(403, 'Forbidden'));
    const onSignedIn = setup();
    await submit();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your account is not registered for this app; ask an admin',
    );
    expect(signOutSession).toHaveBeenCalled();
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it('shows a notice carried in from the guard until the user starts typing', async () => {
    setup('Your account is not registered for this app; ask an admin to add you.');
    expect(screen.getByRole('alert')).toHaveTextContent('not registered');
    await userEvent.type(screen.getByLabelText(/Email/), 'a');
    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  it('locks the form while the request runs', async () => {
    let finish: () => void = () => undefined;
    vi.mocked(signInWithPassword).mockReturnValue(
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
    );
    vi.mocked(gql).mockResolvedValue({ viewer: TRADER });
    setup();
    await submit();
    expect(screen.getByRole('button', { name: 'Sign in' })).toHaveAttribute('aria-busy', 'true');
    finish();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Sign in' })).not.toHaveAttribute(
        'aria-busy',
        'true',
      );
    });
  });
});
