/**
 * The help drawer restriction (ADR 0051): HelpDrawer, HelpLead and HelpSection may be imported
 * only by src/features/guide-help; anywhere else in src/ the lint message names the ADR and
 * the add-guide-content skill. Reads the resolved ESLint config of a file (no parsing).
 */
import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';

interface Restriction {
  name: string;
  importNames?: string[];
  message: string;
}

// One ESLint for every case: building one loads the whole config, which alone took over the
// default 5 s under a loaded `make check` (PR 279), so the cases also get a longer timeout.
const eslint = new ESLint({ cwd: process.cwd() });
const TIMEOUT_MS = 30_000;

async function drawerRestriction(file: string): Promise<Restriction | undefined> {
  const config = (await eslint.calculateConfigForFile(file)) as {
    rules: Record<string, [unknown, { paths: Restriction[] }]>;
  };
  const options = config.rules['no-restricted-imports']?.[1];
  return options?.paths.find((p) => p.name === '@algotrade/ui' && p.importNames);
}

describe('help drawer import restriction', () => {
  it.each([
    'src/pages/trader-explore/Example.tsx',
    'src/widgets/feature-table/ui/Example.tsx',
    'src/features/screener-builder/ui/Example.tsx',
    'src/features/screener-builder/ui/Example.test.tsx',
    'src/entities/feature/ui/Example.tsx',
    'src/shared/lib/Example.ts',
  ])(
    'forbids the three components in %s, naming ADR 0051 and the skill',
    async (file) => {
      const found = await drawerRestriction(file);
      expect(found?.importNames).toEqual(['HelpDrawer', 'HelpLead', 'HelpSection']);
      expect(found?.message).toContain('ADR 0051');
      expect(found?.message).toContain('.claude/skills/add-guide-content');
    },
    TIMEOUT_MS,
  );

  it.each([
    'src/features/guide-help/ui/Example.tsx',
    'src/features/guide-help/ui/Example.test.tsx',
    'src/features/guide-help/model/Example.ts',
  ])(
    'allows them in %s',
    async (file) => {
      expect(await drawerRestriction(file)).toBeUndefined();
    },
    TIMEOUT_MS,
  );
});
