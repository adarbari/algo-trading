import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const auth = {
  getSession: vi.fn(),
  signInWithPassword: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChange: vi.fn(),
};
const createClient = vi.fn(() => ({ auth }));

vi.mock('@supabase/supabase-js', () => ({ createClient }));

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

const CONFIGURED = { url: 'https://p.supabase.test', key: 'anon' };

beforeEach(() => {
  auth.getSession.mockResolvedValue({
    data: { session: { access_token: 'tok-1', user: { email: 'a@b.co' } } },
  });
  auth.signInWithPassword.mockResolvedValue({ error: null });
  auth.signOut.mockResolvedValue({ error: null });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('with Supabase configured', () => {
  it('creates the client once, from the keys, persisting the session', async () => {
    const { accessToken } = await load(CONFIGURED);
    await accessToken();
    await accessToken();
    expect(createClient).toHaveBeenCalledTimes(1);
    const [url, key, options] = createClient.mock.calls[0] as unknown as [
      string,
      string,
      { auth: { persistSession: boolean } },
    ];
    expect([url, key]).toEqual(['https://p.supabase.test', 'anon']);
    expect(options.auth.persistSession).toBe(true);
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
    expect(createClient).not.toHaveBeenCalled();
  });

  it('says why sign-in cannot work', async () => {
    const { signInWithPassword } = await load({});
    await expect(signInWithPassword('a@b.co', 'pw')).rejects.toMatchObject({
      code: 'not_configured',
      message: expect.stringContaining('VITE_SUPABASE_URL') as unknown,
    });
  });
});
