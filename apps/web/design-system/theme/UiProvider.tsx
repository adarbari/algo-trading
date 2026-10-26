/**
 * The design-system root: loads fonts, tokens and base styles, and applies theme, density and
 * the up/down palette to the document. Wrap the app (and every story) in it exactly once.
 *
 * Fonts are self-hosted from @fontsource (Sora 600, Figtree 400/500/600, DM Mono 400/500,
 * Latin subset only): bundled by Vite, so no third-party request, no layout shift waiting on a
 * CDN, identical glyphs in CI screenshots and offline.
 */
import '@fontsource/sora/latin-600.css';
import '@fontsource/figtree/latin-400.css';
import '@fontsource/figtree/latin-500.css';
import '@fontsource/figtree/latin-600.css';
import '@fontsource/dm-mono/latin-400.css';
import '@fontsource/dm-mono/latin-500.css';
import '../tokens/tokens.css';
import './base.css';

import { useEffect, type ReactNode } from 'react';

import type { DensityName } from '../tokens';

/** `dark` is the default (dark-first); `system` follows `prefers-color-scheme`. */
export type Theme = 'dark' | 'light' | 'system';
export type UpDownPalette = 'standard' | 'cvd';

export interface UiProviderProps {
  /** Colour theme; dark by default, `system` follows the OS. */
  theme?: Theme;
  /** `compact` (default, data screens) or `comfortable`. */
  density?: DensityName;
  /** `cvd`: colour-blind-safe up/down (blue/orange) instead of green/red. */
  upDown?: UpDownPalette;
  children: ReactNode;
}

export function UiProvider({
  theme = 'dark',
  density = 'compact',
  upDown = 'standard',
  children,
}: UiProviderProps) {
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-density', density);
    root.setAttribute('data-updown', upDown);
  }, [theme, density, upDown]);
  return children;
}
