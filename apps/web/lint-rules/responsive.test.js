/** The rule 9 check (lint-rules/responsive.js): which `<Grid>` usages it reports. */
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

describe('algotrade/grid-collapses', () => {
  it.each([
    '<Grid columns={2} collapse="lg" />',
    '<Grid collapse="md" />',
    '<Grid columns="main-aside" collapse="lg" />',
    '<Grid columns={1} />',
    '<Grid columns="1" />',
    '<Stack columns={2} />',
  ])('accepts %s', (jsx) => {
    expect(lint(`const x = ${jsx};`)).toEqual([]);
  });

  it.each([
    '<Grid columns={2} />',
    '<Grid />',
    '<Grid columns="main-aside" gap={4} />',
    '<Grid columns={3} collapse="none" />',
  ])('reports %s', (jsx) => {
    const found = lint(`const x = ${jsx};`);
    expect(found).toHaveLength(1);
    expect(found[0]).toContain('[ADR 0025 rule 9]');
    expect(found[0]).toContain('.claude/skills/responsive-ui');
  });
});
