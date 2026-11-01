/**
 * The sign-up question's guard (ADR 0083, amendment 2026-11-01): a signed-in viewer who has no
 * stored start tab is sent to `/onboarding` before any trader page. A failed read never locks
 * anyone out: the page opens and the question comes at the next visit.
 */
import type { QueryClient } from '@tanstack/react-query';
import { redirect, useNavigate } from '@tanstack/react-router';

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

/** `beforeLoad` step of the trader layout, run after the workspace guard. */
export async function onboardingGuard({
  context,
  location,
}: {
  context: { queryClient: QueryClient };
  location: { pathname: string };
}): Promise<void> {
  if (location.pathname === ONBOARDING_PATH) return;
  let answered = true;
  try {
    const { ensureTraderPreferences } = await import('@/entities/trader-preferences');
    answered = (await ensureTraderPreferences(context.queryClient)).defaultTab !== null;
  } catch {
    return;
  }
  // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
  if (!answered) throw redirect({ to: ONBOARDING_PATH });
}
