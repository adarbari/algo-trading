/**
 * The TRADER workspace's layout route (the default workspace): pathless, so its sections sit
 * at the top level (`/ideas`, `/explore`, ...), behind the workspace guard; a viewer with no
 * stored start tab is sent to `/onboarding` by `OnboardingRedirect` (never blocking the page, no extra request). It also holds
 * `/settings` (from the account menu; the one sign-up question while it is unanswered), a route
 * around the product, not a section of it.
 */
import { createRoute } from '@tanstack/react-router';

import { lazyPage } from '@/shared/lib/lazy';

import { WorkspaceLayout } from '../../layouts';
import { TRADER, workspaceGuard } from '../../workspaces';
import { OnboardingRedirect } from '../../workspaces/onboarding-redirect';
import { pageRoute } from '../page-loader';
import { rootRoute } from '../root';

const guard = workspaceGuard('trader');

export const traderRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'trader',
  beforeLoad: guard,
  component: () => (
    <>
      <WorkspaceLayout workspace={TRADER} />
      <OnboardingRedirect />
    </>
  ),
});

const SettingsScreen = lazyPage(() => import('../../workspaces/settings-screen'), 'SettingsScreen');

export const settingsRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'settings',
  ...pageRoute(SettingsScreen),
  component: SettingsScreen,
});
