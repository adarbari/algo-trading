/**
 * The chart's colours and font, read from the CSS tokens of the active theme (the canvas cannot
 * use CSS variables), and a hook that changes whenever the theme does: `data-theme` /
 * `data-updown` on <html> (UiProvider) or the system colour scheme under `system`.
 */
import { useEffect, useState } from 'react';

import { SERIES, type Series } from '../../tokens';
import type { EngineTheme } from './engine';

export function readTheme(element: Element): EngineTheme {
  const css = getComputedStyle(element);
  const read = (name: string) => css.getPropertyValue(name).trim();
  const fontSize = Number.parseFloat(read('--font-size-xs'));
  return {
    surface: read('--color-surface'),
    text: read('--color-text'),
    text2: read('--color-text-2'),
    muted: read('--color-muted'),
    borderSoft: read('--color-border-soft'),
    control: read('--color-control'),
    row: read('--color-row'),
    accentSoft: read('--color-accent-soft'),
    track: read('--color-track'),
    fontFamily: read('--font-sans'),
    fontSize: Number.isFinite(fontSize) ? fontSize : 11.5,
    bands: {
      positive: read('--color-positive-bg'),
      warning: read('--color-warning-bg'),
      negative: read('--color-negative-bg'),
      neutral: read('--color-neutral-bg'),
      info: read('--color-info-bg'),
      accent: read('--color-accent-soft'),
    },
    tones: {
      positive: read('--color-positive'),
      warning: read('--color-warning'),
      negative: read('--color-negative'),
      neutral: read('--color-neutral'),
      info: read('--color-info'),
      accent: read('--color-accent'),
    },
    borders: {
      positive: read('--color-positive-border'),
      warning: read('--color-warning-border'),
      negative: read('--color-negative-border'),
      neutral: read('--color-neutral-border'),
      info: read('--color-info-border'),
      accent: read('--color-accent-border'),
    },
    series: Object.fromEntries(SERIES.map((s) => [s, read(`--color-${s}`)])) as Record<
      Series,
      string
    >,
  };
}

/** A number that changes when the active theme changes (re-read the tokens then). */
export function useThemeVersion(): number {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const bump = () => {
      setVersion((v) => v + 1);
    };
    const observer = new MutationObserver(bump);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'data-updown'],
    });
    const scheme =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-color-scheme: dark)')
        : undefined;
    scheme?.addEventListener('change', bump);
    return () => {
      observer.disconnect();
      scheme?.removeEventListener('change', bump);
    };
  }, []);
  return version;
}
