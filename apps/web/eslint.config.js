/**
 * ESLint for apps/web (ADR 0025). Each concern lives in its own module under lint-rules/:
 *   base.js          TypeScript, React, hooks, accessibility (rule 8), Query, Storybook
 *   layers.js        rules 1-2: layers import downward; slices only through index.ts
 *   restrictions.js  rules 3-4: component-only UI, no styling outside design-system, HTTP only
 *                    in shared/api, which libraries each layer may use
 * Every message names its rule, docs/ui/architecture.md and the skill that explains the fix.
 */
import { base } from './lint-rules/base.js';
import { layers } from './lint-rules/layers.js';
import { appRestrictions, designSystemRestrictions } from './lint-rules/restrictions.js';

export default [
  {
    ignores: [
      'dist/',
      'storybook-static/',
      'playwright-report/',
      'test-results/',
      'node_modules/',
      'src/shared/api/generated/',
      '!.storybook',
    ],
  },
  ...base,
  layers,
  ...appRestrictions,
  designSystemRestrictions,
];
