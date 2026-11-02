import { describe, expect, it } from 'vitest';

import { legacyRoutes } from './redirects';

/** What the legacy route at `path` redirects to for these params and search. */
function target(path: string, params: Record<string, string> = {}, search: object = {}) {
  const route = legacyRoutes.find((r) => (r.options as { path?: string }).path === path);
  const run = route?.options.beforeLoad as ((a: unknown) => unknown) | undefined;
  try {
    run?.({ params, search });
  } catch (thrown) {
    const { options } = thrown as { options: { to: string; params?: object; search?: object } };
    return options;
  }
  throw new Error(`no redirect from ${path}`);
}

describe('the old Screeners and edge-builder URLs', () => {
  it('send the list to the Test start, keeping its search', () => {
    expect(target('screeners', {}, { f: 'owner:mine;picked:1..', q: 'vrp' })).toMatchObject({
      to: '/test',
      search: { f: 'owner:mine;picked:1..', q: 'vrp' },
    });
  });

  it('send a screener to its Result, its Builder and a new one to Expert, keeping returnTo', () => {
    expect(target('screeners/$id', { id: 'my-vrp' }, { f: 'x' })).toMatchObject({
      to: '/test/result/$id',
      params: { id: 'my-vrp' },
    });
    expect(target('screeners/$id/edit', { id: 'my-vrp' }, { returnTo: 'momo' })).toMatchObject({
      to: '/test/expert/$id',
      params: { id: 'my-vrp' },
      search: { returnTo: 'momo' },
    });
    expect(target('screeners/new', {}, { returnTo: '.new' })).toMatchObject({
      to: '/test/expert',
      search: { returnTo: '.new' },
    });
  });

  it('send the edge builder to the setup step', () => {
    expect(target('edges/new')).toMatchObject({ to: '/test/setup' });
    expect(target('edges/$id/edit', { id: 'mine' })).toMatchObject({
      to: '/test/setup/$id',
      params: { id: 'mine' },
    });
  });
});
