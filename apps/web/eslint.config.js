/**
 * ESLint for apps/web (ADR 0025). Each concern lives in its own module under lint-rules/:
 *   base.js          TypeScript, React, hooks, accessibility (rule 8), Query, Storybook
 *   layers.js        rules 1-2: layers import downward; slices only through index.ts
 *   restrictions.js  rules 3-4: component-only UI, no styling outside design-system, HTTP only
 *                    in shared/api, which libraries each layer may use; lightweight-charts only
 *                    in design-system/components/Chart
 *   columns.js       read model WEB 4: table columns only from the column factories
 *   views.js         read model WEB 7: a table's saved view only through features/table-view
 * Every message names its rule, docs/ui/architecture.md and the skill that explains the fix.
 */
import { base } from './lint-rules/base.js';
import { columnFactories } from './lint-rules/columns.js';
import { layers } from './lint-rules/layers.js';
import {
  appRestrictions,
  chartRestrictions,
  designSystemRestrictions,
} from './lint-rules/restrictions.js';
import { viewAdapter } from './lint-rules/views.js';

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
  chartRestrictions,
  columnFactories,
  viewAdapter,
];
