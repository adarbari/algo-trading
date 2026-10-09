/**
 * `/login`: the sign-in page, outside the workspaces (no guard, no top bar). Opening it while
 * already signed in (or with the API's auth off) goes straight to the default workspace; the
 * guard sends it `?reason=unregistered` when a valid token belongs to no registered user, which
 * signs the session out (so the next visit is a plain sign-in) and says why.
 */
import { createRoute, redirect, useNavigate, useSearch } from '@tanstack/react-router';

import { ensureViewer, NOT_REGISTERED } from '@/entities/viewer';
import { signOutSession } from '@/shared/api';

import { DEFAULT_WORKSPACE } from '../workspaces';
import type { LoginReason } from '../workspaces/guard';
import { rootRoute } from './root';
import { lazyPage } from '@/shared/lib/lazy';

const LoginPage = lazyPage(() => import('@/pages/login'), 'LoginPage');

interface LoginSearch {
  reason?: LoginReason;
}

const home = DEFAULT_WORKSPACE.sections[0]?.path ?? '/ideas';

export const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  validateSearch: (search): LoginSearch =>
    search['reason'] === 'unregistered' ? { reason: 'unregistered' } : {},
  beforeLoad: async ({ search, context }) => {
    if (search.reason === 'unregistered') {
      await signOutSession();
      return;
    }
    const viewer = await ensureViewer(context.queryClient).catch(() => null);
    // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
    if (viewer) throw redirect({ to: home });
  },
  component: function LoginRoute() {
    const navigate = useNavigate();
    const { reason } = useSearch({ from: '/login' });
    return (
      <LoginPage
        notice={reason === 'unregistered' ? NOT_REGISTERED : undefined}
        onSignedIn={() => void navigate({ to: home })}
      />
    );
  },
});
