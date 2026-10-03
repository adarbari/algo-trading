/**
 * jsdom has no layout: every element measures 0 x 0, so a virtualised list (DataTable) would
 * render no rows. `stubElementSize()` gives elements a size for the calling test file.
 */
import { afterAll, beforeAll } from 'vitest';

const KEYS = ['offsetHeight', 'offsetWidth'] as const;

export function stubElementSize(height = 400, width = 1000): void {
  const originals = KEYS.map((key) => Object.getOwnPropertyDescriptor(HTMLElement.prototype, key));
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      get: () => height,
    });
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
      configurable: true,
      get: () => width,
    });
  });
  afterAll(() => {
    KEYS.forEach((key, i) => {
      const original = originals[i];
      if (original) Object.defineProperty(HTMLElement.prototype, key, original);
    });
  });
}
