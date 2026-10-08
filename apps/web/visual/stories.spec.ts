/**
 * Every design-system story, in light and dark: a screenshot compared with the committed
 * baseline, and an axe scan including colour contrast (ADR 0025 rule 6). Stories are read from
 * the static Storybook's index.json, so a new story is covered without editing this file.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { storyFileStem, THEMES } from '../scripts/component-folders';

interface StoryEntry {
  type: string;
  id: string;
  exportName: string;
  importPath: string;
  tags?: string[];
}

const index = JSON.parse(
  readFileSync(new URL('../storybook-static/index.json', import.meta.url), 'utf8'),
) as {
  entries: Record<string, StoryEntry>;
};
// A story tagged `no-screenshot` is exercised by its play function in the unit tests only:
// its click redraws after the render finishes, so a screenshot of it flakes (ds:check rule).
const stories = Object.values(index.entries).filter(
  (entry) => entry.type === 'story' && !entry.tags?.includes('no-screenshot'),
);

/**
 * `a11y.manual`: Storybook's a11y addon otherwise runs axe by itself after every story render
 * (preview `a11y: { test: 'error' }`), and a second axe run started while that one is in flight
 * fails with "Axe is already running". This suite runs the one axe scan per page itself, after
 * the render has finished and the screenshot is taken, so the two never overlap.
 */
const storyUrl = (id: string, theme: string): string =>
  `/iframe.html?id=${id}&viewMode=story&globals=theme:${theme};a11y.manual:!true`;

interface PreviewWindow {
  __STORYBOOK_PREVIEW__?: { currentRender?: { phase?: string } };
}

test.skip(
  process.platform !== 'linux',
  'screenshot baselines are Linux (CI image): run `npm run visual:docker`',
);

for (const story of stories) {
  for (const theme of THEMES) {
    test(`${story.id} (${theme})`, async ({ page }) => {
      await page.goto(storyUrl(story.id, theme));
      await page.locator('#storybook-root').waitFor({ state: 'attached' });
      // The story (including its play / afterEach hooks) has fully rendered.
      await page.waitForFunction(
        () => (window as PreviewWindow).__STORYBOOK_PREVIEW__?.currentRender?.phase === 'finished',
      );
      await page.evaluate(() => document.fonts.ready);
      const folder = join(dirname(story.importPath), '__screenshots__').replace(/^\.\//, '');
      await expect(page).toHaveScreenshot(
        [...folder.split('/'), `${storyFileStem(story.exportName)}.${theme}.png`],
        {
          fullPage: true,
        },
      );
      // Exactly one axe run per page load, awaited (light and dark are separate tests / pages).
      const axe = await new AxeBuilder({ page }).include('#storybook-root').analyze();
      expect(axe.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
    });
  }
}
