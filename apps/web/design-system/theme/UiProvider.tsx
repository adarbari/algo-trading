/**
 * The design-system root: loads fonts, tokens and base styles, and applies theme, density and
 * the up/down palette to the document. Wrap the app (and every story) in it exactly once.
 */
import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';
import '../tokens/tokens.css';
import './base.css';

import { useEffect, type ReactNode } from 'react';

import type { DensityName } from '../tokens';

export type Theme = 'light' | 'dark' | 'system';
export type UpDownPalette = 'standard' | 'cvd';

export interface UiProviderProps {
  /** `system` follows `prefers-color-scheme`. */
  theme?: Theme;
  density?: DensityName;
  /** `cvd`: colour-blind-safe up/down (blue/orange) instead of green/red. */
  upDown?: UpDownPalette;
  children: ReactNode;
}

function setAttribute(name: string, value: string | undefined): void {
  const root = document.documentElement;
  if (value === undefined) root.removeAttribute(name);
  else root.setAttribute(name, value);
}

export function UiProvider({
  theme = 'system',
  density = 'compact',
  upDown = 'standard',
  children,
}: UiProviderProps) {
  useEffect(() => {
    setAttribute('data-theme', theme === 'system' ? undefined : theme);
    setAttribute('data-density', density);
    setAttribute('data-updown', upDown);
  }, [theme, density, upDown]);
  return children;
}
