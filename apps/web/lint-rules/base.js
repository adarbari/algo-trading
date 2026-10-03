/**
 * Language and React rules for all TypeScript in apps/web: typed typescript-eslint, React,
 * hooks, accessibility (rule 8: eslint-plugin-jsx-a11y strict), TanStack Query, Storybook.
 */
import js from '@eslint/js';
import pluginQuery from '@tanstack/eslint-plugin-query';
import prettier from 'eslint-config-prettier';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import storybook from 'eslint-plugin-storybook';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export const base = [
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
      globals: { ...globals.browser },
    },
    rules: {
      '@typescript-eslint/restrict-template-expressions': ['error', { allowNumber: true }],
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      'no-console': 'error',
    },
  },
  {
    files: ['**/*.{ts,tsx}'],
    ...react.configs.flat.recommended,
    ...react.configs.flat['jsx-runtime'],
    settings: { react: { version: '19' } },
  },
  reactHooks.configs.flat['recommended-latest'] ?? reactHooks.configs['recommended-latest'],
  jsxA11y.flatConfigs.strict,
  ...pluginQuery.configs['flat/recommended'],
  ...storybook.configs['flat/recommended'],
  {
    files: [
      'scripts/**',
      'e2e/**',
      'visual/**',
      '*.config.{js,ts}',
      'lint-rules/**',
      '.storybook/**',
    ],
    languageOptions: { globals: { ...globals.node } },
    rules: { 'no-console': 'off' },
  },
  {
    files: ['**/*.js'],
    ...tseslint.configs.disableTypeChecked,
  },
  prettier,
];
