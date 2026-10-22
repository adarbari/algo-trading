import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { active } from './active-client';
import { forgetVersions, observeVersions } from './versions';

const headers = (generation?: number, release?: string) =>
  new Headers({
    ...(generation === undefined ? {} : { 'x-config-generation': String(generation) }),
    ...(release === undefined ? {} : { 'x-release-id': release }),
  });

const key = (name: string, variables: Record<string, unknown> = {}) =>
  ['gql', name, variables] as const;
const observe = (name: string, h: Headers, variables: Record<string, unknown> = {}) => {
  observeVersions(key(name, variables), h);
};

/** A client holding one answer per operation; `stale()` lists the operations marked stale. */
function seeded(names: string[]) {
  const client = new QueryClient();
  for (const name of names) client.setQueryData(['gql', name, {}], { name });
  active.client = client;
  return () => {
    return names.filter((name) => client.getQueryState(['gql', name, {}])?.isInvalidated === true);
  };
}

beforeEach(() => {
  forgetVersions();
});

describe('observeVersions', () => {
  it('invalidates the user-keyed queries when the generation rises, not the one just answered', () => {
    const stale = seeded(['Ideas', 'Views', 'RegimeBands']);
    observe('Ideas', headers(2));
    observe('Views', headers(2));
    observe('RegimeBands', headers()); // shared: no generation header
    expect(stale()).toEqual([]); // the first sight of a generation only sets the baseline
    observe('Ideas', headers(4));
    expect(stale()).toEqual(['Views']); // another tab wrote; shared and the answered one stay
  });

  it('ignores the same generation', () => {
    const stale = seeded(['Ideas', 'Views']);
    observe('Ideas', headers(4));
    observe('Views', headers(4));
    observe('Ideas', headers(4));
    expect(stale()).toEqual([]);
  });

  it('refetches an answer sent before a write once it has landed, and spares nothing else', () => {
    vi.useFakeTimers();
    const stale = seeded(['Ideas', 'Views']);
    observe('Ideas', headers(3));
    observe('Views', headers(2)); // in flight across the write, arriving after the newer one
    expect(stale()).toEqual([]);
    vi.advanceTimersByTime(0); // not runAllTimers: that would also expire the cache entries
    expect(stale()).toEqual(['Views']);
    vi.useRealTimers();
  });

  it('spares only the answered variables of the operation, not its other keys', () => {
    const client = new QueryClient();
    active.client = client;
    client.setQueryData(key('Ideas', { day: 'a' }), 1);
    client.setQueryData(key('Ideas', { day: 'b' }), 2);
    observe('Ideas', headers(2), { day: 'a' });
    observe('Ideas', headers(3), { day: 'a' });
    expect(client.getQueryState(key('Ideas', { day: 'a' }))?.isInvalidated).toBe(false);
    expect(client.getQueryState(key('Ideas', { day: 'b' }))?.isInvalidated).toBe(true);
  });

  it('invalidates the other queries when the serving release changes', () => {
    const stale = seeded(['Ideas', 'RegimeBands', 'GuideIndex']);
    observe('Ideas', headers(2, 'r1'));
    observe('Ideas', headers(2, 'r1'));
    expect(stale()).toEqual([]);
    observe('RegimeBands', headers(undefined, 'r2'));
    expect(stale()).toEqual(['Ideas', 'GuideIndex']);
  });

  it('does not take an older release for a change, nor orders them by text', () => {
    const stale = seeded(['Ideas', 'Views']);
    observe('Ideas', headers(undefined, '2026-10-21.12.f1'));
    observe('Ideas', headers(undefined, '2026-10-21.9.f1')); // a late answer of the old release
    observe('Ideas', headers(undefined, '2026-10-21.12.f1'));
    expect(stale()).toEqual([]);
    observe('Ideas', headers(undefined, '2026-10-21.100.f1')); // 100 > 12, though "100" < "12"
    expect(stale()).toEqual(['Views']);
  });

  it('does nothing without a header, and forgets a user who leaves', () => {
    const stale = seeded(['Ideas', 'Views']);
    observe('Ideas', headers());
    observe('Views', headers(2));
    forgetVersions();
    observe('Ideas', headers(1)); // the next user's counter starts elsewhere
    expect(stale()).toEqual([]);
  });
});
