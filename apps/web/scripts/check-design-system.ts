/**
 * Design-system completeness check (`npm run ds:check`, ADR 0011 / ADR 0025 rule 6). Every
 * primitives/<Name> and components/<Name> folder has:
 *   - Name.tsx, Name.module.css, index.ts, Name.stories.tsx, Name.test.tsx;
 *   - stories for the canonical states (Default, Loading, Empty, Error, Dense), or the state
 *     named in `parameters.states.notApplicable` with the reason;
 *   - a `Narrow` story when its CSS has an `@container` or `(pointer: coarse)` rule, or the
 *     reason it has none in `parameters.states.notApplicable` (ADR 0025 rule 10);
 *   - a story whose `play` clicks settles before the screenshot (`await waitFor(` or
 *     `await expect(` after the last click), or is tagged `tags: ['no-screenshot']`;
 *   - an axe accessibility assertion in its unit test;
 *   - committed screenshots for every story in light and dark (__screenshots__/, made by
 *     `npm run visual:update`; compared in CI).
 * `--baselines` (`npm run visual:missing`) makes the missing ones, in the CI Playwright image.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { componentFolders, storyFileStem, THEMES, type ComponentFolder } from './component-folders';

const STATES = ['Default', 'Loading', 'Empty', 'Error', 'Dense'] as const;
const RESPONSIVE_GUIDE =
  'see .claude/skills/responsive-ui and docs/ui/architecture.md (ADR 0025 rule 10)';
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

export const NO_SCREENSHOT_TAG = 'no-screenshot';

/** Each story export with its source text. */
function storyBlocks(source: string): { name: string; body: string }[] {
  const starts = [...source.matchAll(/^export const (\w+)\s*:/gm)];
  return starts.map((match, i) => ({
    name: match[1] as string,
    body: source.slice(match.index, starts[i + 1]?.index ?? source.length),
  }));
}

const isTagged = (body: string): boolean =>
  new RegExp(`tags:\\s*\\[[^\\]]*['"]${NO_SCREENSHOT_TAG}['"]`).test(body);

/** Stories tagged `tags: ['no-screenshot']`: the visual suite skips them, so they have no PNG. */
export function noScreenshotStories(source: string): Set<string> {
  return new Set(
    storyBlocks(source)
      .filter((b) => isTagged(b.body))
      .map((b) => b.name),
  );
}

/** Stories whose `play` clicks and then neither settles nor opts out of the screenshot. */
export function unsettledClickStories(source: string): string[] {
  return storyBlocks(source)
    .filter(({ body }) => {
      const lastClick = body.lastIndexOf('.click(');
      if (lastClick < 0 || lastClick < body.indexOf('play:') || !body.includes('play:'))
        return false;
      return !/await (waitFor|expect)\(/.test(body.slice(lastClick)) && !isTagged(body);
    })
    .map((b) => b.name);
}

/** The screenshot files a component's stories lack (every story, light and dark). */
export function missingScreenshots(folder: ComponentFolder): string[] {
  const storiesPath = join(folder.dir, `${folder.name}.stories.tsx`);
  const stories = existsSync(storiesPath) ? readFileSync(storiesPath, 'utf8') : '';
  const shots = existsSync(join(folder.dir, '__screenshots__'))
    ? readdirSync(join(folder.dir, '__screenshots__'))
    : [];
  const unshot = noScreenshotStories(stories);
  return storyNames(stories)
    .filter((story) => !unshot.has(story))
    .flatMap((story) => THEMES.map((theme) => `${storyFileStem(story)}.${theme}.png`))
    .filter((file) => !shots.includes(file));
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
  for (const story of unsettledClickStories(stories)) {
    found.push(
      `story '${story}' clicks in play and does not settle: add 'await waitFor(' or 'await expect(' after the click, or tags: ['${NO_SCREENSHOT_TAG}'] (a screenshot taken mid-redraw flakes; docs/ci.md "Flaky specs")`,
    );
  }
  const cssPath = join(dir, `${name}.module.css`);
  const css = existsSync(cssPath) ? readFileSync(cssPath, 'utf8') : '';
  if (
    /@container|pointer:\s*coarse/.test(css) &&
    !names.includes('Narrow') &&
    !skipped.has('Narrow')
  ) {
    found.push(
      `its CSS has an @container or pointer: coarse rule but no 'Narrow' story (narrow decorator from design-system/testing), or give the reason in parameters.states.notApplicable: ${RESPONSIVE_GUIDE}`,
    );
  }
  const testPath = join(dir, `${name}.test.tsx`);
  if (existsSync(testPath) && !readFileSync(testPath, 'utf8').includes('expectNoA11yViolations')) {
    found.push(`${name}.test.tsx has no accessibility assertion (expectNoA11yViolations)`);
  }
  for (const file of missingScreenshots(folder)) {
    found.push(`missing screenshot __screenshots__/${file} (npm run visual:missing makes it)`);
  }
  return found;
}

/**
 * Makes the baselines a new story lacks (never touches an existing one): builds Storybook, then
 * runs the visual suite with `--update-snapshots=missing` in the CI Playwright image (Docker off
 * Linux), so the PNGs are byte-comparable. 1: Docker is not running.
 */
function makeBaselines(): number {
  const missing = componentFolders()
    .filter((folder) => missingScreenshots(folder).length > 0)
    .map((folder) => folder.name);
  if (missing.length === 0) {
    console.log('ds:baselines: every story has its light and dark baseline');
    return 0;
  }
  const linux = process.platform === 'linux';
  if (!linux && spawnSync('docker', ['info'], { stdio: 'ignore' }).status !== 0) {
    console.error(`ds:baselines: ${missing.join(', ')} lack baselines: start Docker, then rerun`);
    return 1;
  }
  const grep = `--grep='${missing.join('|')}'`;
  const visual = ['npm', 'run', 'visual', '--', '--update-snapshots=missing', grep];
  const steps: [string, string[]][] = [
    ['npm', ['run', 'storybook:build']],
    linux ? ['npm', visual.slice(1)] : ['scripts/in-playwright-docker.sh', visual],
  ];
  for (const [command, args] of steps) {
    if (spawnSync(command, args, { stdio: 'inherit' }).status !== 0) return 1;
  }
  return 0;
}

function main(): number {
  if (process.argv.includes('--baselines')) return makeBaselines();
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
