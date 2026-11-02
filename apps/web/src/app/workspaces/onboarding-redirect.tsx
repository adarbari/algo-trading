/**
 * The sign-up question's redirect (ADR 0083, amendment 2026-11-01): a signed-in trader with no
 * stored start tab is sent to the question (served at `/settings`). It never blocks a page and adds no request: the
 * answer rides on the shell's `Appearance` read. A failed read never locks anyone out, the
 * question comes at the next visit.
 */
import { useNavigate } from '@tanstack/react-router';
import { useEffect } from 'react';

import { useStartTabUnanswered } from '@/entities/appearance';

/** Renders nothing: sends a viewer who has not answered the question to it. */
export function OnboardingRedirect() {
  const navigate = useNavigate();
  const unanswered = useStartTabUnanswered(true) === true;
  useEffect(() => {
    if (unanswered && window.location.pathname !== '/settings') {
      void navigate({ to: '/settings', replace: true });
    }
  }, [unanswered, navigate]);
  return null;
}
