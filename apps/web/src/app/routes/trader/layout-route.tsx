/**
 * The TRADER workspace's layout route (the default workspace): pathless, so its sections sit
 * at the top level (`/ideas`, `/explore`, ...), behind the workspace guard; a viewer with no
 * stored start tab is sent to `/onboarding` by `OnboardingRedirect` (never blocking the page). It also holds the
 * two routes around the product, not sections of it: `/settings` (from the account menu) and
 * `/onboarding` (the one sign-up question).
 */
import { createRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';

import { lazyPage } from '@/shared/lib/lazy';

import { WorkspaceLayout } from '../../layouts';
import { TRADER, workspaceGuard } from '../../workspaces';
import { pageRoute } from '../page-loader';
import { rootRoute } from '../root';

const guard = workspaceGuard('trader');
// Loaded on demand: the entry chunk carries only the import (perf-budgets.json).
const OnboardingRedirect = lazy(() =>
  import('../../workspaces/onboarding').then((m) => ({ default: m.OnboardingRedirect })),
);

export const traderRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'trader',
  beforeLoad: guard,
  component: () => (
    <>
      <WorkspaceLayout workspace={TRADER} />
      <Suspense fallback={null}>
        <OnboardingRedirect />
      </Suspense>
    </>
  ),
});

const SettingsPage = lazyPage(() => import('@/pages/settings'), 'SettingsPage');
const OnboardingPage = lazyPage(() => import('../../workspaces/onboarding'), 'OnboardingScreen');

export const settingsRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'settings',
  ...pageRoute(SettingsPage),
  component: SettingsPage,
});

export const onboardingRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'onboarding',
  ...pageRoute(OnboardingPage),
  component: OnboardingPage,
});
