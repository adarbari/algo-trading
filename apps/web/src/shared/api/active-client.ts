/**
 * The app's one query client, for code that runs when a page's chunk loads (a hovered link
 * preloads it) and so has no component to ask.
 */
import type { QueryClient } from '@tanstack/react-query';

/** `client` is set when the app makes its client; undefined in tests that render a page alone. */
export const active: { client?: QueryClient } = {};
