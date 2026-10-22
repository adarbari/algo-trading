import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { active } from './active-client';
import { forgetVersions, installVersions, observeVersions } from './versions';

const headers = (generation?: number, release?: string) =>
  new Headers({
    ...(generation === undefined ? {} : { 'x-config-generation': String(generation) }),
    ...(release === undefined ? {} : { 'x-release-id': release }),
  });

const key = (name: string, variables: Record<string, unknown> = {}) =>
  ['gql', name, variables] as const;
/** Observes an answer of a query that is in the cache, as a running fetch's is. */
const answer = (k: readonly unknown[], h: Headers) => {
  active.client?.getQueryCache().build(active.client, { queryKey: k });
  observeVersions(k, h);
};
const observe = (name: string, h: Headers, variables: Record<string, unknown> = {}) => {
  answer(key(name, variables), h);
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

describe('the signed-in user', () => {
  it('ends the counters when the viewer is another user or none, not when it is the same', () => {
    const client = new QueryClient();
    active.client = client;
    installVersions(client);
    const viewer = ['gql', 'Viewer', {}] as const;
    const ideas = ['gql', 'Ideas', {}] as const;
    client.setQueryData(viewer, { id: 'ann' });
    answer(key('Ideas'), headers(5));
    client.setQueryData(viewer, { id: 'ann' }); // refetched: the same user
    client.setQueryData(ideas, 1);
    answer(key('Views'), headers(6)); // a rise: the baseline of 5 stands
    expect(client.getQueryState(ideas)?.isInvalidated).toBe(true);
    client.setQueryData(viewer, null); // signed out
    client.setQueryData(ideas, 1);
    answer(key('Ideas'), headers(2)); // the next user's counter starts elsewhere
    answer(key('Views'), headers(3)); // a rise from their baseline of 2
    expect(client.getQueryState(ideas)?.isInvalidated).toBe(true);
  });
});

describe('the signed-in user, seeded', () => {
  it('knows a viewer loaded before it was installed, and installs once per client', () => {
    const client = new QueryClient();
    active.client = client;
    const viewer = ['gql', 'Viewer', {}] as const;
    client.setQueryData(viewer, { id: 'ann' });
    const subscribe = vi.spyOn(client.getQueryCache(), 'subscribe');
    installVersions(client);
    installVersions(client); // a second page chunk asks again
    answer(key('Ideas'), headers(5));
    client.setQueryData(viewer, null); // signed out: the counters end
    client.setQueryData(key('Ideas'), 1);
    answer(key('Ideas'), headers(2)); // the next user's counter starts elsewhere
    answer(key('Views'), headers(3));
    expect(client.getQueryState(key('Ideas'))?.isInvalidated).toBe(true);
    expect(subscribe).toHaveBeenCalledTimes(1);
  });

  it('ignores an answer whose query left the cache (a user who has gone)', () => {
    const stale = seeded(['Ideas', 'Views']);
    observe('Ideas', headers(9));
    observeVersions(key('Gone'), headers(20)); // removed on sign-out while in flight
    observe('Views', headers(10)); // not 20 + 1: the gone answer set no baseline
    expect(stale()).toEqual(['Ideas']);
    observe('Ideas', headers(10));
    expect(stale()).toEqual(['Ideas']); // and nothing is refetched as late
  });
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

  it('refetches an answer sent before a write once its data has landed, however late', async () => {
    const client = new QueryClient();
    active.client = client;
    const late = key('Views');
    let land: (value: string) => void = () => undefined;
    // the fetch is still running (no observer) when the newer generation has been seen
    const fetching = client.query({
      queryKey: late,
      queryFn: () =>
        new Promise<string>((resolve) => {
          land = resolve;
        }),
    });
    observe('Ideas', headers(3));
    observeVersions(late, headers(2)); // answered before the write, its data not stored yet
    await new Promise((resolve) => setTimeout(resolve, 5)); // a timer would have fired by now
    expect(client.getQueryState(late)?.isInvalidated).toBe(false);
    land('pre-write');
    await fetching;
    await vi.waitFor(() => {
      expect(client.getQueryState(late)?.isInvalidated).toBe(true);
    });
  });

  it('keys a query as its hook did, not as operation and variables', () => {
    const client = new QueryClient();
    active.client = client;
    const compare = ['gql', 'EdgesPage', { compare: 'e1' }] as const; // runs EdgeCompare
    const other = ['gql', 'EdgesPage', {}] as const;
    client.setQueryData(compare, 1);
    client.setQueryData(other, 2);
    answer(other, headers(2));
    answer(other, headers(3));
    expect(client.getQueryState(compare)?.isInvalidated).toBe(true);
    expect(client.getQueryState(other)?.isInvalidated).toBe(false);
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
