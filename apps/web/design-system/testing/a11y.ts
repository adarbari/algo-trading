/**
 * Accessibility assertion for design-system unit tests (axe-core in jsdom). Colour contrast
 * needs real rendering, so it is checked per story and theme in visual/stories.spec.ts.
 */
import axe from 'axe-core';
import { expect } from 'vitest';

/**
 * Floating UI's focus guards (overlays) get role="button" only on Safari, for VoiceOver; jsdom
 * reports Apple as its vendor, so in unit tests they look like unnamed buttons. In Chromium (the
 * screenshot suite's axe run) they are aria-hidden. Excluded here for that reason only.
 */
const FOCUS_GUARDS = '[data-floating-ui-focus-guard]';

export async function expectNoA11yViolations(container: Element): Promise<void> {
  const result = await axe.run(
    { include: [container], exclude: [[FOCUS_GUARDS]] },
    { rules: { 'color-contrast': { enabled: false } } },
  );
  const found = result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length} node(s))`);
  expect(found, 'axe accessibility violations').toEqual([]);
}
