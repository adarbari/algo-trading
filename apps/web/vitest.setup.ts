/**
 * Vitest setup: DOM matchers for Testing Library, a clean DOM after each test, the one
 * layout API jsdom lacks that components call (scrollIntoView: keeps an active option visible),
 * and a 20 s timeout for the integration-style tests (a page, widget or feature rendered with
 * its Query hooks, and the script tests that run ESLint in-process): under `make check
 * WORKERS=2` they take 5 to 15 s, and the 5 s default read as flakes (docs/ci.md).
 */
import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, expect, vi } from 'vitest';

const INTEGRATION_STYLE = /\/(pages|widgets|features)\/|\/scripts\//;
export const INTEGRATION_TEST_TIMEOUT_MS = 20_000;

beforeAll(() => {
  if (INTEGRATION_STYLE.test(expect.getState().testPath ?? '')) {
    vi.setConfig({ testTimeout: INTEGRATION_TEST_TIMEOUT_MS });
  }
});

afterEach(() => {
  cleanup();
});

Element.prototype.scrollIntoView = function scrollIntoView() {
  // jsdom has no layout: nothing to scroll.
};
