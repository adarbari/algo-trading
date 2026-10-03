/**
 * Accessibility assertion for design-system unit tests (axe-core in jsdom). Colour contrast
 * needs real rendering, so it is checked per story and theme in visual/stories.spec.ts.
 */
import axe from 'axe-core';
import { expect } from 'vitest';

export async function expectNoA11yViolations(container: Element): Promise<void> {
  const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
  const found = result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length} node(s))`);
  expect(found, 'axe accessibility violations').toEqual([]);
}
