/**
 * The sign-up question's redirect (ADR 0083, amendment 2026-11-01): a signed-in trader with no
 * stored start tab is sent to the question (served at `/settings`). It never blocks a page and adds no request: the
 * answer rides on the shell's `Appearance` read. A failed read never locks anyone out, the
 * question comes at the next visit.
 */
import { Navigate } from '@tanstack/react-router';

import { useStartTabUnanswered } from '@/entities/appearance';

/** Renders nothing, or sends a viewer who has not answered the question to it. */
export function OnboardingRedirect() {
  const unanswered = useStartTabUnanswered() === true;
  return unanswered && window.location.pathname !== '/settings' ? (
    <Navigate to="/settings" replace />
  ) : null;
}
