/**
 * Rule 1 + 2 (ADR 0025): layers import only downward and slices only through their public
 * index.ts. eslint-plugin-boundaries classifies every file into an element and checks each
 * import against the policies below (default: disallow).
 *
 *   app -> pages -> widgets -> features -> entities -> shared -> @algotrade/ui
 *
 * Inside a slice any file may import any other; across slices only `index.ts`. Slices of the
 * same layer never import each other (compose them one layer up), except entities, which may
 * reference another entity's public index. The design system never imports app code.
 */
import boundaries from 'eslint-plugin-boundaries';

import { message, PAGE_SKILL } from './guide.js';

const SLICE_LAYERS = ['page', 'widget', 'feature', 'entity'];

export const elements = [
  { type: 'ds-tokens', pattern: 'design-system/tokens' },
  { type: 'ds-theme', pattern: 'design-system/theme' },
  { type: 'ds-testing', pattern: 'design-system/testing' },
  { type: 'ds-primitive', pattern: 'design-system/primitives/*', capture: ['name'] },
  { type: 'ds-component', pattern: 'design-system/components/*', capture: ['name'] },
  { type: 'app', pattern: 'src/app' },
  { type: 'page', pattern: 'src/pages/*', capture: ['slice'] },
  { type: 'widget', pattern: 'src/widgets/*', capture: ['slice'] },
  { type: 'feature', pattern: 'src/features/*', capture: ['slice'] },
  { type: 'entity', pattern: 'src/entities/*', capture: ['slice'] },
  { type: 'shared', pattern: 'src/shared/*', capture: ['segment'] },
  // Last, so it only gets what nothing above matched: the package entry design-system/index.ts.
  { type: 'ds-entry', pattern: 'design-system' },
];

const index = (type) => ({ element: { type }, file: { path: '**/index.ts' } });
const sameSlice = (type) => ({
  element: { type, captured: { slice: '{{from.element.captured.slice}}' } },
});
const ui = { element: { type: 'ds-entry' }, file: { path: 'design-system/index.ts' } };
const shared = index('shared');
const below = {
  page: ['widget', 'feature', 'entity'],
  widget: ['feature', 'entity'],
  feature: ['entity'],
  entity: [],
};

const layerPolicies = SLICE_LAYERS.map((type) => ({
  from: { element: { type } },
  allow: { to: [sameSlice(type), ...below[type].map(index), shared, ui] },
}));

// Allow policies carry no message: a violation means no allow matched, so the rule's default
// message (below) explains it; the disallow policies at the end name the common mistakes.
const policies = [
  {
    from: { element: { type: 'app' } },
    allow: {
      to: [
        { element: { type: 'app' } },
        ...['page', 'widget', 'feature', 'entity', 'shared'].map(index),
        ui,
      ],
    },
  },
  ...layerPolicies,
  {
    from: { element: { type: 'entity' } },
    allow: { to: index('entity') },
  },
  {
    from: { element: { type: 'shared' } },
    allow: {
      to: [
        { element: { type: 'shared', captured: { segment: '{{from.element.captured.segment}}' } } },
        {
          element: { type: 'shared', captured: { segment: 'config' } },
          file: { path: '**/index.ts' },
        },
        {
          element: { type: 'shared', captured: { segment: 'lib' } },
          file: { path: '**/index.ts' },
        },
      ],
    },
  },
  // Design system: the entry (index.ts and the kind indexes) re-exports folders; components
  // build on primitives and tokens; nothing in it imports app code.
  {
    from: { element: { type: 'ds-entry' } },
    allow: {
      to: [
        { element: { type: 'ds-entry' } },
        ...['ds-primitive', 'ds-component', 'ds-theme', 'ds-tokens'].map(index),
      ],
    },
  },
  ...['ds-primitive', 'ds-component'].map((type) => ({
    from: { element: { type } },
    allow: {
      to: [
        { element: { type, captured: { name: '{{from.element.captured.name}}' } } },
        index('ds-primitive'),
        ...(type === 'ds-component' ? [index('ds-component')] : []),
        index('ds-tokens'),
        index('ds-testing'),
      ],
    },
  })),
  // The theme loads the generated tokens.css and the token types.
  {
    from: { element: { type: 'ds-theme' } },
    allow: { to: [{ element: { type: 'ds-theme' } }, { element: { type: 'ds-tokens' } }] },
  },
  { from: { element: { type: 'ds-tokens' } }, allow: { to: { element: { type: 'ds-tokens' } } } },
  { from: { element: { type: 'ds-testing' } }, allow: { to: { element: { type: 'ds-testing' } } } },
  // Last, so their messages win: the two mistakes made most often.
  ...['page', 'widget', 'feature'].map((type) => ({
    from: { element: { type } },
    disallow: {
      to: { element: { type, captured: { slice: '!{{from.element.captured.slice}}' } } },
    },
    message: message(
      1,
      `a ${type} never imports another ${type} ({{dependency.source}}): compose both one layer up (in a ${type === 'feature' ? 'widget or page' : type === 'widget' ? 'page' : 'route in src/app'}).`,
      PAGE_SKILL,
    ),
  })),
];

/** Applied to src/ and design-system/ sources. */
export const layers = {
  files: ['src/**/*.{ts,tsx}', 'design-system/**/*.{ts,tsx}'],
  plugins: { boundaries },
  settings: {
    'boundaries/elements': elements,
    'boundaries/include': ['src/**/*', 'design-system/**/*'],
    'import/resolver': { typescript: { project: './tsconfig.app.json' }, node: true },
  },
  rules: {
    'boundaries/dependencies': [
      'error',
      {
        default: 'disallow',
        message: message(
          '1-2',
          '{{from.element.types}} may not import {{dependency.source}}: import only from lower layers (app -> pages -> widgets -> features -> entities -> shared -> @algotrade/ui), other slices only through their public index.ts, never a sibling slice of the same layer.',
          PAGE_SKILL,
        ),
        policies,
      },
    ],
    'boundaries/no-unknown-files': 'error',
  },
};
