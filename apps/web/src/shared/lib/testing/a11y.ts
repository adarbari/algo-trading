/**
 * Test support for app tests (widgets, pages): the axe accessibility assertion in jsdom.
 * Colour contrast needs real rendering, so it is checked in the e2e and visual suites. Only
 * test files import this module (never re-exported from shared/lib's index).
 */
import axe from 'axe-core';
import { expect } from 'vitest';

/** Floating UI's focus guards look like unnamed buttons in jsdom (see design-system/testing). */
const FOCUS_GUARDS = '[data-floating-ui-focus-guard]';

export async function expectNoA11yViolations(container: Element): Promise<void> {
  const result = await axe.run(
    { include: [container], exclude: [[FOCUS_GUARDS]] },
    { rules: { 'color-contrast': { enabled: false } } },
  );
  const found = result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length} node(s))`);
  expect(found, 'axe accessibility violations').toEqual([]);
}
