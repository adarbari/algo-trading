/**
 * The `/settings` route's component, loaded lazily with its pages: the sign-up question while the
 * viewer has not answered it (the first signed-in visit lands here, see `onboarding-redirect.tsx`;
 * ADR 0083, amendment 2026-11-01), then Ideas once it is answered; Settings from then on.
 */
import { useNavigate } from '@tanstack/react-router';

import { useStartTabUnanswered } from '@/entities/appearance';
import { OnboardingPage } from '@/pages/onboarding';
import { SettingsPage } from '@/pages/settings';

export function SettingsScreen() {
  const navigate = useNavigate();
  const unanswered = useStartTabUnanswered(true) === true;
  return unanswered ? (
    <OnboardingPage
      onDone={() => {
        void navigate({ to: '/ideas' });
      }}
    />
  ) : (
    <SettingsPage />
  );
}
