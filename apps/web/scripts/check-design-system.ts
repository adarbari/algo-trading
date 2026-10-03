/**
 * Design-system completeness check (`npm run ds:check`, ADR 0011 / ADR 0025 rule 6). Every
 * primitives/<Name> and components/<Name> folder has:
 *   - Name.tsx, Name.module.css, index.ts, Name.stories.tsx, Name.test.tsx;
 *   - stories for the canonical states (Default, Loading, Empty, Error, Dense), or the state
 *     named in `parameters.states.notApplicable` with the reason;
 *   - an axe accessibility assertion in its unit test;
 *   - committed screenshots for every story in light and dark (__screenshots__/, made by
 *     `npm run visual:update`; compared in CI).
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { componentFolders, storyFileStem, THEMES, type ComponentFolder } from './component-folders';

const STATES = ['Default', 'Loading', 'Empty', 'Error', 'Dense'] as const;
const GUIDE = 'see .claude/skills/add-ui-component and docs/ui/architecture.md (ADR 0025 rule 6)';

/** Story export names in a CSF file, in file order. */
export function storyNames(source: string): string[] {
  return [...source.matchAll(/^export const (\w+)\s*:/gm)].map((m) => m[1] as string);
}

/** States declared not applicable (`notApplicable: { Loading: 'reason', ... }`). */
export function notApplicable(source: string): Set<string> {
  const block = /notApplicable:\s*\{([^}]*)\}/s.exec(source)?.[1] ?? '';
  return new Set([...block.matchAll(/(\w+):\s*['"`][^'"`]{10,}/g)].map((m) => m[1] as string));
}

export function problems(folder: ComponentFolder): string[] {
  const found: string[] = [];
  const { name, dir } = folder;
  if (!/^[A-Z][A-Za-z0-9]+$/.test(name))
    found.push(`folder name must be PascalCase (the component name)`);
  for (const file of [
    `${name}.tsx`,
    `${name}.module.css`,
    'index.ts',
    `${name}.stories.tsx`,
    `${name}.test.tsx`,
  ]) {
    if (!existsSync(join(dir, file))) found.push(`missing ${file}`);
  }
  const storiesPath = join(dir, `${name}.stories.tsx`);
  const stories = existsSync(storiesPath) ? readFileSync(storiesPath, 'utf8') : '';
  const names = storyNames(stories);
  const skipped = notApplicable(stories);
  for (const state of STATES) {
    if (!names.includes(state) && !skipped.has(state)) {
      found.push(
        `no '${state}' story: export one, or give the reason in parameters.states.notApplicable`,
      );
    }
  }
  const testPath = join(dir, `${name}.test.tsx`);
  if (existsSync(testPath) && !readFileSync(testPath, 'utf8').includes('expectNoA11yViolations')) {
    found.push(`${name}.test.tsx has no accessibility assertion (expectNoA11yViolations)`);
  }
  const shots = existsSync(join(dir, '__screenshots__'))
    ? readdirSync(join(dir, '__screenshots__'))
    : [];
  for (const story of names) {
    for (const theme of THEMES) {
      const file = `${storyFileStem(story)}.${theme}.png`;
      if (!shots.includes(file))
        found.push(`missing screenshot __screenshots__/${file} (npm run visual:update)`);
    }
  }
  return found;
}

function main(): number {
  const report = componentFolders().flatMap((folder) =>
    problems(folder).map((p) => `${folder.rel}: ${p}`),
  );
  if (report.length === 0) {
    console.log('ds:check: every design-system component is complete');
    return 0;
  }
  console.error(`ds:check: incomplete design-system components (${GUIDE}):`);
  for (const line of report) console.error(`  ${line}`);
  return 1;
}

if (import.meta.url === `file://${process.argv[1]}`) process.exit(main());
