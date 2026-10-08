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

import { problems } from './check-design-system';

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
