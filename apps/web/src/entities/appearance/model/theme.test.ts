import { readFileSync } from 'node:fs';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { isThemeChoice, readDeviceTheme, THEME_KEY, writeDeviceTheme } from './theme';

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe('the device copy of the theme', () => {
  it('round-trips a choice and ignores anything else', () => {
    expect(readDeviceTheme()).toBeUndefined();
    writeDeviceTheme('light');
    expect(readDeviceTheme()).toBe('light');
    window.localStorage.setItem(THEME_KEY, 'sepia');
    expect(readDeviceTheme()).toBeUndefined();
    expect(isThemeChoice('system')).toBe(true);
    expect(isThemeChoice('sepia')).toBe(false);
  });

  it('survives storage being blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readDeviceTheme()).toBeUndefined();
    expect(() => {
      writeDeviceTheme('dark');
    }).not.toThrow();
  });

  it('is the key and the values the inline script in index.html reads', () => {
    const html = readFileSync('index.html', 'utf8');
    expect(html).toContain(`localStorage.getItem('${THEME_KEY}')`);
    for (const theme of ['light', 'dark', 'system']) expect(html).toContain(`'${theme}'`);
  });
});
