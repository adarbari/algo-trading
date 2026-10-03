/**
 * Vitest setup: DOM matchers for Testing Library, a clean DOM after each test, and the one
 * layout API jsdom lacks that components call (scrollIntoView: keeps an active option visible).
 */
import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});

Element.prototype.scrollIntoView = function scrollIntoView() {
  // jsdom has no layout: nothing to scroll.
};
