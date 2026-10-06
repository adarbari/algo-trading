/** What a failed sign-in says, in plain words (the login page shows it above the form). */
import { ApiError, AuthFailure } from '@/shared/api';

/** The API accepted the token but the caller is not in the registry (ADR 0040: 403). */
export const NOT_REGISTERED =
  'Your account is not registered for this app; ask an admin to add you.';

/** The message for a sign-in that failed: Supabase's refusal, or the API's 403 on `viewer`. */
export function signInMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) return NOT_REGISTERED;
  if (error instanceof AuthFailure) {
    if (error.code === 'invalid_credentials') return 'Wrong email or password.';
    if (error.code === 'email_not_confirmed') {
      return 'Your email is not confirmed yet: open the link in the invitation email, then sign in.';
    }
    if (error.code === 'over_request_rate_limit' || error.code === 'over_email_send_rate_limit') {
      return 'Too many attempts: wait a minute, then try again.';
    }
    return error.message;
  }
  if (error instanceof ApiError && error.status === 401) {
    return 'The server did not accept the sign-in; try again.';
  }
  return error instanceof Error ? error.message : 'Sign-in failed; try again.';
}
