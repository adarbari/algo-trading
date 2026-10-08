/** The rule 10 check (lint-rules/responsive.js): which `<Grid>` usages it reports. */
import { Linter } from 'eslint';
import tsParser from '@typescript-eslint/parser';
import { describe, expect, it } from 'vitest';

import { responsive } from './responsive.js';

const linter = new Linter({ configType: 'flat' });

function lint(code) {
  return linter
    .verify(
      code,
      [
        {
          files: ['**/*.tsx'],
          languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } } },
          plugins: responsive.plugins,
          rules: responsive.rules,
        },
      ],
      'page.tsx',
    )
    .map((m) => m.message);
}

const UI = "import { Grid, Stack } from '@algotrade/ui';\n";

describe('algotrade/grid-collapses', () => {
  it.each([
    '<Grid columns={2} collapse="lg" />',
    '<Grid collapse="md" />',
    '<Grid collapse={"md"} />',
    '<Grid columns="main-aside" collapse="lg" />',
    '<Grid columns={1} />',
    '<Grid columns="1" />',
    '<Stack columns={2} />',
    '<Grid {...props} />',
  ])('accepts %s', (jsx) => {
    expect(lint(`${UI}const x = ${jsx};`)).toEqual([]);
  });

  it("ignores a Grid that is not the design system's", () => {
    expect(lint("import { Grid } from 'other';\nconst x = <Grid columns={2} />;")).toEqual([]);
  });

  it.each([
    [UI, '<Grid columns={2} />'],
    [UI, '<Grid />'],
    [UI, '<Grid columns="main-aside" gap={4} />'],
    [UI, '<Grid columns={3} collapse="none" />'],
    [UI, '<Grid columns={3} collapse={"none"} />'],
    ["import { Grid as G } from '@algotrade/ui';\n", '<G columns={2} />'],
    ["import * as ui from '@algotrade/ui';\n", '<ui.Grid columns={2} />'],
  ])('reports %s%s', (imports, jsx) => {
    const found = lint(`${imports}const x = ${jsx};`);
    expect(found).toHaveLength(1);
    expect(found[0]).toContain('[ADR 0025 rule 10]');
    expect(found[0]).toContain('.claude/skills/responsive-ui');
  });
});
