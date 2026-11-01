/**
 * The sign-up question (ADR 0083, amendment 2026-11-01): a signed-in trader with no stored start
 * tab is sent to `/onboarding`. The check never blocks a page (it would add a serial round trip
 * to every first load): `OnboardingRedirect` reads the choice beside the page's own reads and
 * redirects when it arrives; a failed read never locks anyone out, the question comes at the
 * next visit. Loaded lazily by the trader layout (the entry chunk carries only the import).
 */
import { useNavigate, useRouterState } from '@tanstack/react-router';
import { useEffect } from 'react';

import { useTraderPreferences } from '@/entities/trader-preferences';
import { OnboardingPage } from '@/pages/onboarding';

export const ONBOARDING_PATH = '/onboarding';

/** The question's route component: the page, then Ideas once it is answered. */
export function OnboardingScreen() {
  const navigate = useNavigate();
  return (
    <OnboardingPage
      onDone={() => {
        void navigate({ to: '/ideas' });
      }}
    />
  );
}

/** Renders nothing: sends a viewer who has not answered the question to it. */
export function OnboardingRedirect() {
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const unanswered = useTraderPreferences().data?.defaultTab === null;
  useEffect(() => {
    if (unanswered && pathname !== ONBOARDING_PATH) {
      void navigate({ to: ONBOARDING_PATH, replace: true });
    }
  }, [unanswered, pathname, navigate]);
  return null;
}
