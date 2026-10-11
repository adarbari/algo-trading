import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const auth = {
  initialize: vi.fn(),
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
  auth.initialize.mockResolvedValue({ error: null });
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
  it('reads the session only after the client finished its own start-up (no second refresh)', async () => {
    const order: string[] = [];
    let finish: (value: unknown) => void = () => undefined;
    auth.initialize.mockImplementation(() => {
      order.push('initialize');
      return new Promise((resolve) => (finish = resolve));
    });
    auth.getSession.mockImplementation(() => {
      order.push('getSession');
      return Promise.resolve({ data: { session: null } });
    });
    const { accessToken } = await load(CONFIGURED);
    const read = accessToken();
    await Promise.resolve();
    expect(order).toEqual(['initialize']);
    finish({ error: null });
    await read;
    expect(order).toEqual(['initialize', 'getSession']);
  });

  it('shares one session read between concurrent callers (one refresh, not one each)', async () => {
    let release: (value: unknown) => void = () => undefined;
    auth.getSession.mockReturnValue(new Promise((resolve) => (release = resolve)));
    const { accessToken, currentSession } = await load(CONFIGURED);
    const reads = Promise.all([accessToken(), accessToken(), currentSession()]);
    release({ data: { session: { access_token: 'tok-2', user: { email: 'a@b.co' } } } });
    expect(await reads).toEqual(['tok-2', 'tok-2', { email: 'a@b.co' }]);
    expect(auth.getSession).toHaveBeenCalledTimes(1);
    auth.getSession.mockResolvedValue({ data: { session: null } });
    expect(await accessToken()).toBeNull();
    expect(auth.getSession).toHaveBeenCalledTimes(2);
  });

  it('has no background refresh ticker: the one refresh is the shared session read', async () => {
    // auth-js's ticker refreshes on its own, racing the read; with an expired token both sent the
    // spent refresh token (e2e "an expired token is refreshed" saw two calls).
    let refreshes = 0;
    auth.getSession.mockImplementation(async () => {
      refreshes += 1;
      await Promise.resolve();
      return { data: { session: { access_token: 'tok-2', user: { email: 'a@b.co' } } } };
    });
    const { accessToken } = await load(CONFIGURED);
    await Promise.all(Array.from({ length: 8 }, () => accessToken()));
    expect(refreshes).toBe(1);
    expect(AuthClient.mock.calls[0]?.[0]).toMatchObject({ autoRefreshToken: false });
  });

  it('reads the session under a browser-wide lock so two tabs never refresh with the same token', async () => {
    const held: string[] = [];
    const request = vi.fn((name: string, _options: unknown, read: () => Promise<unknown>) => {
      held.push(name);
      return read();
    });
    vi.stubGlobal('navigator', { locks: { request } });
    try {
      const { accessToken } = await load(CONFIGURED);
      await accessToken();
      expect(held.length).toBeGreaterThan(0);
      expect(new Set(held)).toEqual(new Set(['algotrade-session-read']));
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('still reads under the lock where AbortSignal.timeout does not exist (Safari 15.x)', async () => {
    const signals: unknown[] = [];
    const request = vi.fn(
      (_name: string, options: { signal: unknown }, read: () => Promise<unknown>) => {
        signals.push(options.signal);
        return read();
      },
    );
    vi.stubGlobal('navigator', { locks: { request } });
    const original = Object.getOwnPropertyDescriptor(AbortSignal, 'timeout');
    Object.defineProperty(AbortSignal, 'timeout', { value: undefined, configurable: true });
    try {
      const { accessToken } = await load(CONFIGURED);
      await expect(accessToken()).resolves.toBe('tok-1');
      expect(signals).toHaveLength(1);
      expect(signals[0]).toBeInstanceOf(AbortSignal);
    } finally {
      if (original) Object.defineProperty(AbortSignal, 'timeout', original);
      vi.unstubAllGlobals();
    }
  });

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
        autoRefreshToken: false,
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
    await vi.waitFor(() => {
      expect(auth.onAuthStateChange).toHaveBeenCalledTimes(2);
    });
    emit('SIGNED_IN', { user: { email: 'a@b.co' } });
    emit('SIGNED_OUT', null);
    expect(seen).toEqual([{ email: 'a@b.co' }, null]);
    stop();
    expect(unsubscribe).toHaveBeenCalled();
  });

  it('registers auth listeners only after the start-up read (their initial read would refresh again)', async () => {
    let finish: (value: unknown) => void = () => undefined;
    auth.getSession.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { subscribeSession } = await load(CONFIGURED);
    const stop = subscribeSession(() => undefined);
    const skipped = subscribeSession(() => undefined);
    skipped();
    await Promise.resolve();
    expect(auth.onAuthStateChange).not.toHaveBeenCalled();
    finish({ data: { session: null } });
    await vi.waitFor(() => {
      expect(auth.onAuthStateChange).toHaveBeenCalledTimes(2);
    });
    stop();
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
