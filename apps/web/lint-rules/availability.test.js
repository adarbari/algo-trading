/** The rule 11 check (lint-rules/availability.js): which reads of a gap it reports. */
import { Linter } from 'eslint';
import tsParser from '@typescript-eslint/parser';
import { describe, expect, it } from 'vitest';

import { availability } from './availability.js';

const linter = new Linter({ configType: 'flat' });

function lint(code) {
  return linter
    .verify(
      code,
      [
        {
          files: ['**/*.tsx'],
          languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } } },
          plugins: availability.plugins,
          rules: availability.rules,
        },
      ],
      'page.tsx',
    )
    .map((m) => m.message);
}

describe('algotrade-availability/reads-a-gap', () => {
  it.each([
    'const x = value.unknown?.code;',
    'const x = value.unknown.code;',
    'const x = screener.notRun.code;',
    'const x = regime.unknownReason?.cause;',
    'const x = gap.cause;',
    'const x = unknown.cause.links;',
    'const x = unavailable.cause;',
  ])('reports %s', (code) => {
    const found = lint(code);
    expect(found.length).toBeGreaterThan(0);
    expect(found[0]).toContain('[ADR 0025 rule 11]');
    expect(found[0]).toContain('.claude/skills/add-web-page');
  });

  it.each([
    'const x = episode.cause;',
    'const x = error.cause;',
    'const x = value.unknown;',
    'const x = value.unknown?.kind;',
    'const x = response.code;',
    'const x = cells[name].unknown;',
    'const x = unknownText(value.unknown);',
  ])('accepts %s', (code) => {
    expect(lint(code)).toEqual([]);
  });
});
