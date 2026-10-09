/**
 * The browser's Supabase session and the two things a user does to it: sign in and sign out.
 * Signing in checks the API accepts the token (`viewer`) before the page moves on, so a user
 * the registry does not know is told so on the login page and left signed out.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import {
  currentSession,
  signInWithPassword,
  signOutSession,
  subscribeSession,
  type AuthSession,
} from '@/shared/api';

import { signInMessage } from '../model/messages';
import { forgetUser, viewerQuery, type Viewer } from './viewer';

/** The Supabase session: `session` is null when signed out, `ready` once it has been read. */
export function useSession(): { ready: boolean; session: AuthSession | null } {
  const [state, setState] = useState<{ ready: boolean; session: AuthSession | null }>({
    ready: false,
    session: null,
  });
  useEffect(() => {
    let live = true;
    void currentSession().then((session) => {
      if (live) setState((previous) => (previous.ready ? previous : { ready: true, session }));
    });
    const unsubscribe = subscribeSession((session) => {
      if (live) setState({ ready: true, session });
    });
    return () => {
      live = false;
      unsubscribe();
    };
  }, []);
  return state;
}

export interface SignIn {
  /** Resolves with the viewer when signed in; rejects only for a programming error. */
  signIn: (email: string, password: string) => Promise<Viewer | null>;
  pending: boolean;
  /** Why the last attempt failed, in plain words; undefined after `reset` or a success. */
  error: string | undefined;
  reset: () => void;
}

/** Sign in with an email and a password, then confirm the API knows the user. */
export function useSignIn(): SignIn {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: async ({ email, password }: { email: string; password: string }) => {
      await signInWithPassword(email, password);
      // Another user may have been here before: nothing of theirs stays cached.
      client.removeQueries();
      try {
        const viewer = await client.query({ ...viewerQuery(), staleTime: 0 });
        if (!viewer) throw new Error('The server did not accept the sign-in; try again.');
        return viewer;
      } catch (error) {
        await signOutSession();
        throw error;
      }
    },
  });
  return {
    signIn: (email, password) => mutation.mutateAsync({ email, password }).catch(() => null),
    pending: mutation.isPending,
    error: mutation.error ? signInMessage(mutation.error) : undefined,
    reset: mutation.reset,
  };
}

/** Ends the session and forgets everything cached for the user; the viewer becomes null. */
export function useSignOut(): () => Promise<void> {
  const client = useQueryClient();
  return async () => {
    await signOutSession();
    forgetUser(client);
  };
}
