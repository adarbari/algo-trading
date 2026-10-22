/**
 * The app's one query client, for code that runs when a page's chunk loads (a hovered link
 * preloads it) and so has no component to ask; and the two hooks of the version tracking
 * (`versions.ts`, installed by the page-cache chunk so the entry does not carry it).
 */
import type { QueryClient, QueryKey } from '@tanstack/react-query';

/** `client` is set when the app makes its client; undefined in tests that render a page alone. */
export const active: {
  client?: QueryClient;
  observe?: (key: QueryKey | null, headers: Headers) => void;
  forget?: () => void;
} = {};
