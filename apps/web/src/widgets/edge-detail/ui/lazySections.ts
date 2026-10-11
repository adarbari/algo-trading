/**
 * The sections of an edge's page below its head, each its own chunk: the page puts one in a
 * `LazySection` and a `Suspense`, so its code and its data load only when it nears the viewport.
 * They are wrapped here, not in the page, so the page's first paint holds only the head.
 */
import { lazyPage } from '@/shared/lib/lazy';

export const EdgeCompare = lazyPage(() => import('./lowerSections'), 'EdgeCompare');
export const EdgeDefinition = lazyPage(() => import('./lowerSections'), 'EdgeDefinition');
export const EdgeDetails = lazyPage(() => import('./lowerSections'), 'EdgeDetails');
export const EdgeLive = lazyPage(() => import('./lowerSections'), 'EdgeLive');
