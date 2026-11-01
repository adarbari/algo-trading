/**
 * The TRADER workspace's layout route (the default workspace): pathless, so its sections sit
 * at the top level (`/ideas`, `/explore`, ...), behind the workspace guard and the sign-up
 * question (a viewer with no stored start tab goes to `/onboarding` first). It also holds the
 * two routes around the product, not sections of it: `/settings` (from the account menu) and
 * `/onboarding` (the one sign-up question).
 */
import { createRoute, useNavigate } from '@tanstack/react-router';

import { lazyPage } from '@/shared/lib/lazy';

import { WorkspaceLayout } from '../../layouts';
import { TRADER, workspaceGuard } from '../../workspaces';
import { pageRoute } from '../page-loader';
import { rootRoute } from '../root';

const guard = workspaceGuard('trader');

export const traderRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'trader',
  beforeLoad: async (args) => {
    await guard(args);
    // Loaded on demand: the entry chunk carries only the call (perf-budgets.json).
    const { onboardingGuard } = await import('../../workspaces/onboarding');
    await onboardingGuard(args);
  },
  component: () => <WorkspaceLayout workspace={TRADER} />,
});

const SettingsPage = lazyPage(() => import('@/pages/settings'), 'SettingsPage');
const OnboardingPage = lazyPage(() => import('@/pages/onboarding'), 'OnboardingPage');

export const settingsRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'settings',
  ...pageRoute(SettingsPage),
  component: SettingsPage,
});

function Onboarding() {
  const navigate = useNavigate();
  return (
    <OnboardingPage
      onDone={() => {
        void navigate({ to: '/ideas' });
      }}
    />
  );
}

export const onboardingRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'onboarding',
  ...pageRoute(OnboardingPage),
  component: Onboarding,
});
