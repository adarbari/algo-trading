/** The stale-deploy reload script in index.html: runs its text against a fake window. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { runInNewContext } from 'node:vm';

import { describe, expect, it } from 'vitest';

const html = readFileSync(join(import.meta.dirname, '..', 'index.html'), 'utf8');
const source = /<script id="chunk-reload">([\s\S]*?)<\/script>/.exec(html)?.[1] ?? '';

type Listener = (e: Record<string, unknown>) => void;

function setup(storage: 'ok' | 'throws' = 'ok') {
  const listeners = new Map<string, Listener>();
  const data = new Map<string, string>();
  let reloads = 0;
  const sessionStorage =
    storage === 'ok'
      ? {
          getItem: (k: string) => data.get(k) ?? null,
          setItem: (k: string, v: string) => void data.set(k, v),
        }
      : {
          getItem: () => {
            throw new Error('denied');
          },
          setItem: () => {
            throw new Error('denied');
          },
        };
  let now = 1_700_000_000_000;
  runInNewContext(source, {
    addEventListener: (name: string, fn: Listener) => listeners.set(name, fn),
    sessionStorage,
    location: { reload: () => (reloads += 1) },
    Date: { now: () => now },
    Number,
    String,
    RegExp,
  });
  const fire = (name: string, key: 'payload' | 'reason', error: unknown) => {
    const event = {
      [key]: error,
      prevented: false,
      preventDefault: () => (event.prevented = true),
    };
    listeners.get(name)?.(event);
    return event;
  };
  return { fire, reloads: () => reloads, advance: (ms: number) => (now += ms) };
}

const chunk = new TypeError('Failed to fetch dynamically imported module: /assets/E-C8G.js');

describe('index.html chunk-reload script', () => {
  it('is present', () => {
    expect(source).not.toBe('');
  });

  it('reloads on the first failure and prevents the default', () => {
    const s = setup();
    expect(s.fire('vite:preloadError', 'payload', chunk).prevented).toBe(true);
    expect(s.reloads()).toBe(1);
  });

  it('does not reload again within 60 s, and does after', () => {
    const s = setup();
    s.fire('vite:preloadError', 'payload', chunk);
    s.advance(59_000);
    s.fire('vite:preloadError', 'payload', chunk);
    expect(s.reloads()).toBe(1);
    s.advance(2_000);
    s.fire('unhandledrejection', 'reason', chunk);
    expect(s.reloads()).toBe(2);
  });

  it('never loops when storage throws', () => {
    const s = setup('throws');
    s.fire('vite:preloadError', 'payload', chunk);
    expect(s.reloads()).toBe(0);
  });

  it('ignores an unrelated error', () => {
    const s = setup();
    const e = s.fire('unhandledrejection', 'reason', new Error('boom'));
    expect(s.reloads()).toBe(0);
    expect(e.prevented).toBe(false);
  });

  it.each([
    'Failed to fetch dynamically imported module: /a.js',
    'error loading dynamically imported module: /a.js',
    'Importing a module script failed.',
    'Unable to preload CSS for /a.css',
  ])('matches %s', (message) => {
    const s = setup();
    s.fire('unhandledrejection', 'reason', new Error(message));
    expect(s.reloads()).toBe(1);
  });
});
