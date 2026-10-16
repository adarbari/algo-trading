/**
 * A route's page loaded on demand: `React.lazy` over a dynamic import, with `preload` so the
 * router can fetch the chunk on link intent. Not TanStack's `lazyRouteComponent`: its `Lazy`
 * wrapper calls `use()` on a promise it drops once resolved, which React 19 reports as
 * "called use() to suspend in a previous render but did not call use() when it finished".
 *
 * Once the module is loaded (a route loader awaits `preload`) the page renders directly:
 * a `React.lazy` that suspends, even on a settled promise, makes React 19 hold the reveal
 * for its 300 ms Suspense throttle.
 */
import { createElement, lazy, type ComponentType } from 'react';

type Module = Record<string, unknown>;

export function lazyPage<M extends Module, K extends keyof M>(
  importer: () => Promise<M>,
  name: K,
): M[K] & { preload: () => Promise<void> } {
  let loading: Promise<M> | undefined;
  let loaded: ComponentType<Record<string, unknown>> | undefined;
  const load = () =>
    (loading ??= importer().then((m) => {
      loaded = m[name] as ComponentType<Record<string, unknown>>;
      return m;
    }));
  const preload = () => load().then(() => undefined);
  const Lazy = lazy(() => load().then((m) => ({ default: m[name] as ComponentType })));
  const Page = (props: Record<string, unknown>) =>
    createElement((loaded ?? Lazy) as ComponentType<Record<string, unknown>>, props);
  return Object.assign(Page, { preload }) as unknown as M[K] & {
    preload: () => Promise<void>;
  };
}
