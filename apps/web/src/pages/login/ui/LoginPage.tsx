/**
 * The login page (ADR 0040): the design-system LoginForm centred on the page, wired to the
 * viewer entity's sign-in. A failed attempt shows its reason above the form until the user
 * edits a field; `notice` is a reason carried in from elsewhere (the guard found the account
 * is not registered). On success the route moves on (`onSignedIn`).
 */
import { Box, LoginForm, Stack } from '@algotrade/ui';
import { useState } from 'react';

import { useSignIn } from '@/entities/viewer';

export interface LoginPageProps {
  /** A reason to show before any attempt (e.g. the account is not registered). */
  notice?: string | undefined;
  /** Called once the user is signed in and the API knows them. */
  onSignedIn: () => void;
}

export function LoginPage({ notice, onSignedIn }: LoginPageProps) {
  const { signIn, pending, error, reset } = useSignIn();
  const [noticeShown, setNoticeShown] = useState(true);
  const shown = error ?? (noticeShown ? notice : undefined);

  return (
    <Box as="main" padding={6}>
      <Stack align="center">
        <LoginForm
          title="Sign in to algotrade"
          pending={pending}
          error={shown}
          onEdit={() => {
            reset();
            setNoticeShown(false);
          }}
          onSubmit={({ email, password }) => {
            setNoticeShown(false);
            void signIn(email, password).then((viewer) => {
              if (viewer) onSignedIn();
            });
          }}
        />
      </Stack>
    </Box>
  );
}
