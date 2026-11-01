/**
 * The theme choices and this device's copy of the signed-in user's choice (ADR 0085). The stored
 * choice lives on the server (`preferences.toml`); the copy in `localStorage` exists only so the
 * page can set `data-theme` before first paint (the inline script in `index.html` reads the same
 * key: a test keeps them in step). Every read and write is guarded: storage can be blocked.
 */

export const THEMES = ['light', 'dark', 'system'] as const;
export type ThemeChoice = (typeof THEMES)[number];

/** The `localStorage` key of the device copy (also named in `index.html`'s inline script). */
export const THEME_KEY = 'algotrade.theme';

export const isThemeChoice = (value: unknown): value is ThemeChoice =>
  THEMES.includes(value as ThemeChoice);

/** This device's copy of the choice, or `undefined` (none, invalid or storage blocked). */
export function readDeviceTheme(): ThemeChoice | undefined {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return isThemeChoice(stored) ? stored : undefined;
  } catch {
    return undefined;
  }
}

/** Keeps `theme` as this device's copy (best effort). */
export function writeDeviceTheme(theme: ThemeChoice): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage blocked: the server's choice still applies after the first response.
  }
}
