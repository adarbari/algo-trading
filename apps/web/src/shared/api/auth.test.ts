import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const auth = {
  getSession: vi.fn(),
  signInWithPassword: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChange: vi.fn(),
};
// Called with `new`: a plain function returning the stub object.
const AuthClient = vi.fn(function (_options: Record<string, unknown>) {
  return auth;
});

vi.mock('@supabase/auth-js', () => ({ AuthClient }));

/** A fresh copy of the module (it creates its client once) under the given config. */
async function load(config: { url?: string; key?: string }) {
  vi.resetModules();
  vi.doMock('@/shared/config', () => ({
    apiBaseUrl: '/api',
    supabaseUrl: config.url,
    supabaseAnonKey: config.key,
  }));
  return import('./auth');
}

const CONFIGURED = { url: 'https://p.supabase.co', key: 'anon' };

beforeEach(() => {
  auth.getSession.mockResolvedValue({
    data: { session: { access_token: 'tok-1', user: { email: 'a@b.co' } } },
  });
  auth.signInWithPassword.mockResolvedValue({ error: null });
  auth.signOut.mockResolvedValue({ error: null });
  auth.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('with Supabase configured', () => {
  it('creates the client once, with exactly the options supabase-js used', async () => {
    const { accessToken } = await load({ url: 'https://abcd.supabase.co/', key: 'anon' });
    await accessToken();
    await accessToken();
    expect(AuthClient).toHaveBeenCalledTimes(1);
    expect(AuthClient.mock.calls[0]).toEqual([
      {
        url: 'https://abcd.supabase.co/auth/v1',
        headers: { apikey: 'anon', Authorization: 'Bearer anon' },
        storageKey: 'sb-abcd-auth-token',
        flowType: 'implicit',
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    ]);
    expect(AuthClient.mock.calls[0]?.[0]).not.toHaveProperty('lock');
  });

  it('derives the storage key from the project ref, trimming the URL', async () => {
    const { accessToken } = await load({ url: '  https://proj.supabase.co  ', key: 'k' });
    await accessToken();
    expect(AuthClient.mock.calls[0]?.[0]).toMatchObject({
      url: 'https://proj.supabase.co/auth/v1',
      storageKey: 'sb-proj-auth-token',
    });
  });

  it('refuses a plain-http project URL, but allows a local one', async () => {
    const remote = await load({ url: 'http://p.supabase.co', key: 'k' });
    await expect(remote.accessToken()).rejects.toMatchObject({ code: 'insecure_url' });
    expect(AuthClient).not.toHaveBeenCalled();
    const local = await load({ url: 'http://127.0.0.1:54321', key: 'k' });
    await local.accessToken();
    expect(AuthClient.mock.calls[0]?.[0]).toMatchObject({
      url: 'http://127.0.0.1:54321/auth/v1',
      storageKey: 'sb-127-auth-token',
    });
  });

  it('gives the current access token, or null when signed out', async () => {
    const { accessToken } = await load(CONFIGURED);
    await expect(accessToken()).resolves.toBe('tok-1');
    auth.getSession.mockResolvedValue({ data: { session: null } });
    await expect(accessToken()).resolves.toBeNull();
  });

  it('signs in and turns a refusal into an AuthFailure with the code', async () => {
    const { signInWithPassword, AuthFailure } = await load(CONFIGURED);
    await signInWithPassword('a@b.co', 'pw');
    expect(auth.signInWithPassword).toHaveBeenCalledWith({ email: 'a@b.co', password: 'pw' });
    auth.signInWithPassword.mockResolvedValue({
      error: { message: 'Invalid login credentials', code: 'invalid_credentials' },
    });
    await expect(signInWithPassword('a@b.co', 'bad')).rejects.toMatchObject({
      name: 'AuthFailure',
      code: 'invalid_credentials',
    });
    await expect(signInWithPassword('a@b.co', 'bad')).rejects.toBeInstanceOf(AuthFailure);
  });

  it('forwards session changes and stops when unsubscribed', async () => {
    const unsubscribe = vi.fn();
    let emit: (event: string, session: unknown) => void = () => undefined;
    auth.onAuthStateChange.mockImplementation((cb: typeof emit) => {
      emit = cb;
      return { data: { subscription: { unsubscribe } } };
    });
    const { subscribeSession } = await load(CONFIGURED);
    const seen: unknown[] = [];
    const stop = subscribeSession((s) => seen.push(s));
    emit('SIGNED_IN', { user: { email: 'a@b.co' } });
    emit('SIGNED_OUT', null);
    expect(seen).toEqual([{ email: 'a@b.co' }, null]);
    stop();
    expect(unsubscribe).toHaveBeenCalled();
  });

  it('a SIGNED_OUT from elsewhere (another tab) tells the listeners; our own sign-out does not', async () => {
    const callbacks: ((event: string) => void)[] = [];
    auth.onAuthStateChange.mockImplementation((cb: (event: string) => void) => {
      callbacks.push(cb);
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });
    const { accessToken, onUnauthorized, signOutSession } = await load(CONFIGURED);
    await accessToken();
    const listener = vi.fn();
    onUnauthorized(listener);
    callbacks[0]?.('TOKEN_REFRESHED');
    expect(listener).not.toHaveBeenCalled();
    callbacks[0]?.('SIGNED_OUT');
    expect(listener).toHaveBeenCalledTimes(1);
    auth.signOut.mockImplementation(() => {
      callbacks[0]?.('SIGNED_OUT'); // auth-js emits it for the tab's own sign-out too
      return Promise.resolve({ error: null });
    });
    await signOutSession();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('only a SIGNED_OUT without a session signs this tab out; SIGNED_IN, TOKEN_REFRESHED and INITIAL_SESSION never do', async () => {
    const callbacks: ((event: string, session: unknown) => void)[] = [];
    auth.onAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      callbacks.push(cb);
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });
    const { accessToken, onUnauthorized } = await load(CONFIGURED);
    await accessToken();
    const listener = vi.fn();
    onUnauthorized(listener);
    const session = { user: { email: 'a@b.co' } };
    callbacks[0]?.('SIGNED_OUT', session);
    callbacks[0]?.('SIGNED_IN', session);
    callbacks[0]?.('TOKEN_REFRESHED', session);
    callbacks[0]?.('INITIAL_SESSION', session);
    callbacks[0]?.('INITIAL_SESSION', null);
    expect(listener).not.toHaveBeenCalled();
    callbacks[0]?.('SIGNED_OUT', null);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('on a 401 signs out locally and tells the listeners', async () => {
    const { handleUnauthorized, onUnauthorized } = await load(CONFIGURED);
    const listener = vi.fn();
    const off = onUnauthorized(listener);
    await handleUnauthorized();
    expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(listener).toHaveBeenCalledTimes(1);
    off();
    await handleUnauthorized();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('without Supabase keys (the API runs with auth off)', () => {
  it('has no session and no token, and never builds a client', async () => {
    const { accessToken, currentSession, subscribeSession } = await load({});
    await expect(accessToken()).resolves.toBeNull();
    await expect(currentSession()).resolves.toBeNull();
    const seen: unknown[] = [];
    subscribeSession((s) => seen.push(s))();
    expect(seen).toEqual([null]);
    expect(AuthClient).not.toHaveBeenCalled();
  });

  it('says why sign-in cannot work', async () => {
    const { signInWithPassword } = await load({});
    await expect(signInWithPassword('a@b.co', 'pw')).rejects.toMatchObject({
      code: 'not_configured',
      message: expect.stringContaining('VITE_SUPABASE_URL') as unknown,
    });
  });
});
