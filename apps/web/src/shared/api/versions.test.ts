import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it } from 'vitest';

import { active } from './active-client';
import { forgetVersions, observeVersions } from './versions';

const headers = (generation?: number, release?: string) =>
  new Headers({
    ...(generation === undefined ? {} : { 'x-config-generation': String(generation) }),
    ...(release === undefined ? {} : { 'x-release-id': release }),
  });

/** A client holding one answer per operation; `stale()` lists the operations marked stale. */
function seeded(names: string[]) {
  const client = new QueryClient();
  for (const name of names) client.setQueryData(['gql', name, {}], { name });
  active.client = client;
  return () =>
    names.filter((name) => client.getQueryState(['gql', name, {}])?.isInvalidated === true);
}

beforeEach(() => {
  forgetVersions();
});

describe('observeVersions', () => {
  it('invalidates the user-keyed queries when the generation rises, not the one just answered', () => {
    const stale = seeded(['Ideas', 'Views', 'RegimeBands']);
    observeVersions('Ideas', headers(2));
    observeVersions('Views', headers(2));
    observeVersions('RegimeBands', headers()); // shared: no generation header
    expect(stale()).toEqual([]); // the first sight of a generation only sets the baseline
    observeVersions('Ideas', headers(4));
    expect(stale()).toEqual(['Views']); // another tab wrote; shared and the answered one stay
  });

  it('ignores the same or an older generation', () => {
    const stale = seeded(['Ideas', 'Views']);
    observeVersions('Ideas', headers(4));
    observeVersions('Views', headers(4));
    observeVersions('Ideas', headers(4));
    observeVersions('Ideas', headers(2)); // an answer that was in flight before the write
    expect(stale()).toEqual([]);
  });

  it('invalidates the other queries when the serving release changes', () => {
    const stale = seeded(['Ideas', 'RegimeBands', 'GuideIndex']);
    observeVersions('Ideas', headers(2, 'r1'));
    observeVersions('Ideas', headers(2, 'r1'));
    expect(stale()).toEqual([]);
    observeVersions('RegimeBands', headers(undefined, 'r2'));
    expect(stale()).toEqual(['Ideas', 'GuideIndex']);
  });

  it('does nothing without a header, and forgets a user who leaves', () => {
    const stale = seeded(['Ideas', 'Views']);
    observeVersions('Ideas', headers());
    observeVersions('Views', headers(2));
    forgetVersions();
    observeVersions('Ideas', headers(1)); // the next user's counter starts elsewhere
    expect(stale()).toEqual([]);
  });
});
