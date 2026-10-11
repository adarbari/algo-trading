/**
 * The accessibility check every e2e spec shares: axe over the page, with the page settled first.
 * A control still fading between two colours (a button that just became enabled, a hover) is
 * caught mid-transition at a blended colour and fails the contrast rule on a run that is fine
 * a moment later, so the check waits for every CSS transition and animation to finish. An
 * animation that repeats forever (the pulse of a placeholder for a section not yet reached)
 * never finishes and is not waited for.
 */
import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

/** Waits until nothing on the page is animating. */
export async function settled(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const finite = document
      .getAnimations()
      .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity);
    await Promise.all(finite.map((a) => a.finished.catch(() => undefined)));
  });
}

export async function expectAccessible(page: Page): Promise<void> {
  await settled(page);
  const axe = await new AxeBuilder({ page }).analyze();
  expect(
    axe.violations.map(
      (v) => `${v.id}: ${v.help} ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
    ),
  ).toEqual([]);
}
