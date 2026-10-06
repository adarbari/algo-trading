import { describe, expect, it } from 'vitest';

import { ApiError, AuthFailure } from '@/shared/api';

import { NOT_REGISTERED, signInMessage } from './messages';

describe('signInMessage', () => {
  it('says the account is not registered for a 403 from the API', () => {
    expect(signInMessage(new ApiError(403, 'Forbidden'))).toBe(NOT_REGISTERED);
    expect(NOT_REGISTERED).toContain('ask an admin');
  });

  it('puts Supabase refusals in plain words', () => {
    const refused = (code: string | undefined, message = 'raw text') =>
      signInMessage(new AuthFailure(message, code));
    expect(refused('invalid_credentials', 'Invalid login credentials')).toBe(
      'Wrong email or password.',
    );
    expect(refused('email_not_confirmed')).toContain('not confirmed');
    expect(refused('over_request_rate_limit')).toContain('Too many attempts');
    expect(refused(undefined, 'Sign-in is not set up')).toBe('Sign-in is not set up');
  });

  it('never leaks a stack for anything else', () => {
    expect(signInMessage(new ApiError(401, 'Unauthorized'))).toContain('did not accept');
    expect(signInMessage(new Error('offline'))).toBe('offline');
    expect(signInMessage('odd')).toBe('Sign-in failed; try again.');
  });
});
