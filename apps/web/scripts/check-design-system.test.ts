/** The responsive part of the design-system check: a Narrow story where the CSS has container rules. */
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { describe, expect, it, vi } from 'vitest';

vi.mock('./component-folders', () => ({
  componentFolders: () => [],
  storyFileStem: (s: string) => s,
  THEMES: [],
}));

import { noScreenshotStories, problems, unsettledClickStories } from './check-design-system';

function folder(css: string, stories: string): Parameters<typeof problems>[0] {
  const dir = mkdtempSync(join(tmpdir(), 'ds-'));
  writeFileSync(join(dir, 'Box.module.css'), css);
  writeFileSync(join(dir, 'Box.stories.tsx'), stories);
  return { name: 'Box', dir, rel: 'Box' } as Parameters<typeof problems>[0];
}

const STATES = ['Default', 'Loading', 'Empty', 'Error', 'Dense']
  .map((s) => `export const ${s}: Story = {};`)
  .join('\n');
const has = (found: string[]) => found.some((p) => p.includes("no 'Narrow' story"));

describe('Narrow story requirement', () => {
  it('flags a container query without a Narrow story', () => {
    expect(has(problems(folder('@container (width < 720px) {}', STATES)))).toBe(true);
    expect(has(problems(folder('@media (pointer: coarse) {}', STATES)))).toBe(true);
  });
  it('accepts a Narrow story, or a CSS without responsive rules', () => {
    const withNarrow = `${STATES}\nexport const Narrow: Story = {};`;
    expect(has(problems(folder('@container (width < 720px) {}', withNarrow)))).toBe(false);
    expect(has(problems(folder('.a { color: red }', STATES)))).toBe(false);
  });
});

describe('play-with-click requirement', () => {
  const click = "await userEvent.click(canvas.getByRole('button'));";
  const story = (name: string, play: string, extra = '') =>
    `export const ${name}: Story = {\n  ${extra}\n  play: async ({ canvas }) => {\n    ${play}\n  },\n};\n`;
  it('flags a click that is not followed by a settle', () => {
    expect(unsettledClickStories(story('Open', click))).toEqual(['Open']);
    expect(
      unsettledClickStories(story('Open', `await expect(a).toBeVisible();\n${click}`)),
    ).toEqual(['Open']);
  });
  it('accepts a settle after the click, the no-screenshot tag, or no click', () => {
    const settled = `${click}\nawait waitFor(() => expect(a).toBeVisible());`;
    expect(unsettledClickStories(story('Open', settled))).toEqual([]);
    expect(
      unsettledClickStories(story('Open', `${click}\nawait expect(a).toBeVisible();`)),
    ).toEqual([]);
    expect(unsettledClickStories(story('Open', click, "tags: ['no-screenshot'],"))).toEqual([]);
    expect(unsettledClickStories('export const A: Story = { args: {} };')).toEqual([]);
  });
  it('a tagged story needs no committed screenshot', () => {
    const tagged = story('Open', click, "tags: ['no-screenshot'],");
    expect(noScreenshotStories(tagged)).toEqual(new Set(['Open']));
  });
  it('is part of the component check', () => {
    const found = problems(folder('', `${STATES}\n${story('Open', click)}`));
    expect(found.some((p) => p.includes("story 'Open' clicks in play"))).toBe(true);
  });
});
