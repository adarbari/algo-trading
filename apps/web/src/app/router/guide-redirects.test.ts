/** The Guide section once called Playbooks: its old links redirect to the Screeners pages. */
import { isRedirect } from '@tanstack/react-router';
import { describe, expect, it } from 'vitest';

import { router } from './router';

/** What the old path's route throws from `beforeLoad` (a router redirect), as `{ to, params }`. */
const redirectOf = (
  path: string,
  extra: { search?: unknown; hash?: string } = {},
): { to?: string; params?: unknown; search?: unknown; hash?: string } | undefined => {
  const match = router.matchRoutes(path).at(-1);
  const route = router.routesById[match?.routeId as keyof typeof router.routesById];
  try {
    (route.options as { beforeLoad?: (a: unknown) => unknown }).beforeLoad?.({
      params: match?.params,
      search: extra.search ?? {},
      location: { hash: extra.hash ?? '' },
    });
  } catch (thrown) {
    if (isRedirect(thrown))
      return thrown.options as {
        to?: string;
        params?: unknown;
        search?: unknown;
        hash?: string;
      };
    throw thrown;
  }
  return undefined;
};

describe('the legacy Guide Playbooks links', () => {
  it('redirect the index to /guide/screeners', () => {
    expect(redirectOf('/guide/playbooks')?.to).toBe('/guide/screeners');
  });

  it('redirect a page to /guide/screeners/<id>', () => {
    const found = redirectOf('/guide/playbooks/trend_continuation');
    expect(found?.to).toBe('/guide/screeners/$id');
    expect(found?.params).toEqual({ id: 'trend_continuation' });
  });

  it('keep the search params and the hash of the old link', () => {
    const found = redirectOf('/guide/playbooks/pullback', {
      search: { view: 'x' },
      hash: 's2',
    });
    expect(found?.search).toEqual({ view: 'x' });
    expect(found?.hash).toBe('s2');
    expect(redirectOf('/guide/playbooks', { hash: 'top' })?.hash).toBe('top');
  });
});
