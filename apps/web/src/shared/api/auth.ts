/**
 * The Supabase session (ADR 0040 decision 3), inside the one HTTP layer: the Supabase auth client
 * (`@supabase/auth-js`, the part of supabase-js that signs in; ADR 0040 amended)
 * built from `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`, the access token every API request
 * carries as a bearer, sign-in with an email and a password, and the "the API refused the
 * token" signal (`onUnauthorized`) that signs the session out locally. auth-js keeps the
 * session in localStorage and refreshes it; there are no cookies.
 *
 * The client is created on first use. With no keys (a local API running `ALGOTRADE_AUTH=off`)
 * there is no session and no token, and `signInWithPassword` says so instead of failing
 * obscurely.
 */
import { AuthClient } from '@supabase/auth-js';

import { supabaseAnonKey, supabaseUrl } from '@/shared/config';

/** Why a sign-in or sign-out failed: auth-js's error `code` (when it has one) and text. */
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

type Auth = InstanceType<typeof AuthClient>;

let client: Auth | null | undefined;
let signingOut = false;

/** The project's base URL: https, or http only for a local Supabase (the e2e mock, `supabase start`). */
function baseUrl(raw: string): URL {
  const base = new URL(raw.trim().replace(/\/?$/, '/'));
  const local = base.hostname === 'localhost' || base.hostname === '127.0.0.1';
  if (base.protocol !== 'https:' && !(base.protocol === 'http:' && local)) {
    throw new AuthFailure('VITE_SUPABASE_URL must be an https URL.', 'insecure_url');
  }
  return base;
}

function authClient(): Auth | null {
  if (client === undefined) {
    if (supabaseUrl && supabaseAnonKey) {
      const base = baseUrl(supabaseUrl);
      client = new AuthClient({
        url: new URL('auth/v1', base).href,
        headers: { apikey: supabaseAnonKey, Authorization: `Bearer ${supabaseAnonKey}` },
        // The key supabase-js used (sb-<project ref>-auth-token): existing sessions survive.
        storageKey: `sb-${base.hostname.split('.')[0] ?? ''}-auth-token`,
        flowType: 'implicit',
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      });
      // The session ended somewhere else (another tab signed out, or the refresh token was
      // refused): this tab leaves too, at once. Our own sign-out is ignored here: its callers
      // already notify.
      client.onAuthStateChange((event, session) => {
        if (!session && event === 'SIGNED_OUT' && !signingOut) notifyUnauthorized();
      });
    } else {
      client = null;
    }
  }
  return client;
}

/** The current access token, or null when signed out (or when Supabase is not configured). */
export async function accessToken(): Promise<string | null> {
  const auth = authClient();
  if (!auth) return null;
  const { data } = await auth.getSession();
  return data.session?.access_token ?? null;
}

/** The current browser session, or null. */
export async function currentSession(): Promise<AuthSession | null> {
  const auth = authClient();
  if (!auth) return null;
  const { data } = await auth.getSession();
  return data.session ? { email: data.session.user.email } : null;
}

/** Calls `listener` with the session now and on every change (sign-in, sign-out, expiry). */
export function subscribeSession(listener: (session: AuthSession | null) => void): () => void {
  const auth = authClient();
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
  const auth = authClient();
  if (!auth) {
    throw new AuthFailure(
      'Sign-in is not set up: VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are missing.',
      'not_configured',
    );
  }
  const { error } = await auth.signInWithPassword({ email, password });
  if (error) throw new AuthFailure(error.message, error.code);
}

/** Ends the browser session. Local scope: this session only; the stored session goes even when the revoke call fails. */
export async function signOutSession(): Promise<void> {
  signingOut = true;
  try {
    await authClient()?.signOut({ scope: 'local' });
  } finally {
    signingOut = false;
  }
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
  notifyUnauthorized();
}

function notifyUnauthorized(): void {
  unauthorizedListeners.forEach((listener) => {
    listener();
  });
}
