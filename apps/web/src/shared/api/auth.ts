/**
 * The Supabase session (ADR 0040 decision 3), inside the one HTTP layer: the supabase-js client
 * built from `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`, the access token every API request
 * carries as a bearer, sign-in with an email and a password, and the "the API refused the
 * token" signal (`onUnauthorized`) that signs the session out locally. supabase-js keeps the
 * session in localStorage and refreshes it; there are no cookies.
 *
 * The client is created on first use. With no keys (a local API running `ALGOTRADE_AUTH=off`)
 * there is no session and no token, and `signInWithPassword` says so instead of failing
 * obscurely.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

import { supabaseAnonKey, supabaseUrl } from '@/shared/config';

/** Why a sign-in or sign-out failed: supabase-js's error `code` (when it has one) and text. */
export class AuthFailure extends Error {
  readonly code: string | undefined;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'AuthFailure';
    this.code = code;
  }
}

/** A signed-in browser session (the part the app shows). */
export interface AuthSession {
  readonly email: string | undefined;
}

let client: SupabaseClient | null | undefined;

function supabase(): SupabaseClient | null {
  if (client === undefined) {
    client =
      supabaseUrl && supabaseAnonKey
        ? createClient(supabaseUrl, supabaseAnonKey, {
            auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
          })
        : null;
  }
  return client;
}

/** The current access token, or null when signed out (or when Supabase is not configured). */
export async function accessToken(): Promise<string | null> {
  const auth = supabase()?.auth;
  if (!auth) return null;
  const { data } = await auth.getSession();
  return data.session?.access_token ?? null;
}

/** The current browser session, or null. */
export async function currentSession(): Promise<AuthSession | null> {
  const auth = supabase()?.auth;
  if (!auth) return null;
  const { data } = await auth.getSession();
  return data.session ? { email: data.session.user.email } : null;
}

/** Calls `listener` with the session now and on every change (sign-in, sign-out, expiry). */
export function subscribeSession(listener: (session: AuthSession | null) => void): () => void {
  const auth = supabase()?.auth;
  if (!auth) {
    listener(null);
    return () => undefined;
  }
  const { data } = auth.onAuthStateChange((_event, session) => {
    listener(session ? { email: session.user.email } : null);
  });
  return () => {
    data.subscription.unsubscribe();
  };
}

/** Signs in with an email and a password; throws an `AuthFailure` when refused. */
export async function signInWithPassword(email: string, password: string): Promise<void> {
  const auth = supabase()?.auth;
  if (!auth) {
    throw new AuthFailure(
      'Sign-in is not set up: VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are missing.',
      'not_configured',
    );
  }
  const { error } = await auth.signInWithPassword({ email, password });
  if (error) throw new AuthFailure(error.message, error.code);
}

/** Ends the browser session. Local scope: it never needs the network, so it cannot hang. */
export async function signOutSession(): Promise<void> {
  await supabase()?.auth.signOut({ scope: 'local' });
}

const unauthorizedListeners = new Set<() => void>();

/** Calls `listener` whenever the API answers 401 (or the session ends); returns the unsubscribe. */
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

/** The API refused the token: drop the session and tell the app, which shows the login page. */
export async function handleUnauthorized(): Promise<void> {
  await signOutSession();
  unauthorizedListeners.forEach((listener) => {
    listener();
  });
}
