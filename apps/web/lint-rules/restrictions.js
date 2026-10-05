/**
 * Rules 3 + 4 (ADR 0025) for app code (src/): component-only UI, no styling, HTTP only in
 * shared/api, and which libraries each layer may use. `no-restricted-syntax` and
 * `no-restricted-imports` do not merge across config objects, so each layer's full list is
 * built here in one place.
 */
import { message, PAGE_SKILL } from './guide.js';

/** Rule 3: no intrinsic elements, no styling props, no styling values outside design-system/. */
const COMPONENT_ONLY = [
  {
    selector: 'JSXOpeningElement > JSXIdentifier[name=/^[a-z]/]',
    message: message(
      3,
      'no raw HTML/SVG elements outside design-system/: lay out with primitives (Stack, Text, ...) and use components from @algotrade/ui. Missing one? Add it to the design system first.',
    ),
  },
  {
    selector: 'JSXOpeningElement > JSXMemberExpression',
    message: message(
      3,
      'no namespaced/intrinsic elements outside design-system/: use components from @algotrade/ui.',
    ),
  },
  {
    selector: "CallExpression[callee.property.name='createElement']",
    message: message(
      3,
      'no createElement outside design-system/: use components from @algotrade/ui.',
    ),
  },
  {
    selector: 'JSXAttribute[name.name=/^(className|style|dangerouslySetInnerHTML)$/]',
    message: message(
      3,
      'no className / style / dangerouslySetInnerHTML outside design-system/: components expose semantic props and variants instead.',
    ),
  },
];

const STYLING_VALUES = [
  {
    selector: 'Literal[value=/#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-zA-Z])/]',
    message: message(
      3,
      'no hex colours outside design-system/: colour comes from tokens through component props (tone, variant).',
    ),
  },
  {
    selector:
      'TemplateElement[value.raw=/#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-zA-Z])/]',
    message: message(
      3,
      'no hex colours outside design-system/: colour comes from tokens through component props.',
    ),
  },
  {
    selector: 'Literal[value=/\\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color-mix)\\(/]',
    message: message(
      3,
      'no colour functions outside design-system/: colour comes from tokens through component props.',
    ),
  },
  {
    selector: 'Literal[value=/^-?\\d+(?:\\.\\d+)?(?:px|rem|em|vh|vw)$/]',
    message: message(
      3,
      'no CSS lengths outside design-system/: spacing and sizes come from tokens through props (gap, padding, density).',
    ),
  },
];

const HTTP_SYNTAX = [
  {
    selector: "CallExpression[callee.name='fetch'], CallExpression[callee.property.name='fetch']",
    message: message(
      4,
      'only src/shared/api talks HTTP: call the typed client through a TanStack Query hook exported by an entity or feature.',
      PAGE_SKILL,
    ),
  },
  {
    selector: 'NewExpression[callee.name=/^(XMLHttpRequest|WebSocket|EventSource)$/]',
    message: message(4, 'only src/shared/api talks to the network.', PAGE_SKILL),
  },
];

const http = (names) =>
  names.map((name) => ({
    name,
    message: message(4, `${name}: only src/shared/api talks HTTP.`, PAGE_SKILL),
  }));
const HTTP_LIBRARIES = [
  'openapi-fetch',
  'axios',
  'ky',
  'ofetch',
  'superagent',
  'node-fetch',
  'cross-fetch',
  // GraphQL clients (ADR 0037): the one transport is gql() in src/shared/api/graphql.ts over
  // fetch and TanStack Query; Apollo / urql would add a second cache and are not used at all.
  'graphql-request',
  '@apollo/client',
  'urql',
  '@urql/core',
];
const CSS_IN_JS = [
  'styled-components',
  '@emotion/react',
  '@emotion/styled',
  '@emotion/css',
  '@vanilla-extract/css',
  '@stitches/react',
  'styled-jsx',
  'tailwindcss',
  '@pandacss/dev',
  'clsx',
  'classnames',
];

const STYLE_IMPORTS = {
  group: ['*.css', '*.scss', '*.sass', '*.less'],
  message: message(
    3,
    'no stylesheets outside design-system/: styling lives only in design-system CSS Modules.',
  ),
};
const DEEP_UI = {
  group: ['@algotrade/ui/*', '**/design-system/**'],
  message: message(2, 'import the design system only from its public API: `@algotrade/ui`.'),
};

const ROUTER = {
  name: '@tanstack/react-router',
  message: message(
    1,
    'routing belongs to src/app: pages get params as props from their route.',
    PAGE_SKILL,
  ),
};
const QUERY = {
  name: '@tanstack/react-query',
  message: message(
    4,
    'data access goes through hooks exported by entities or features (TanStack Query lives there).',
    PAGE_SKILL,
  ),
};
const REACT_DOM = {
  name: 'react-dom',
  message: message(3, 'react-dom belongs to src/app (mounting) and the design system (portals).'),
};

/**
 * Libraries that only one design-system component may import (ADR 0011: one wrapper each).
 * lightweight-charts: only components/Chart (its engine.ts); everything else draws charts with
 * the Chart component. Floating UI: only the overlay components of the design system.
 */
const CHART_LIBRARY = {
  name: 'lightweight-charts',
  message: message(
    3,
    'lightweight-charts is wrapped by the Chart component (design-system/components/Chart) only: use <Chart> from @algotrade/ui.',
  ),
};
const OVERLAY_LIBRARY = {
  name: '@floating-ui/react',
  message: message(
    3,
    'overlays (Tooltip, Popover, Dialog, Drawer) come from @algotrade/ui; Floating UI stays inside the design system.',
  ),
};

/** Which libraries each layer may not import, beyond the shared bans. */
const LAYER_BANS = {
  app: [],
  pages: [ROUTER, QUERY, REACT_DOM],
  widgets: [ROUTER, QUERY, REACT_DOM],
  features: [ROUTER, REACT_DOM],
  entities: [ROUTER, REACT_DOM],
  'shared/lib': [ROUTER, QUERY, REACT_DOM],
  'shared/config': [ROUTER, QUERY, REACT_DOM],
  'shared/api': [ROUTER, REACT_DOM],
};

function restrictedImports(layer) {
  const httpAllowed = layer === 'shared/api';
  return [
    'error',
    {
      paths: [
        ...(httpAllowed ? [] : http(HTTP_LIBRARIES)),
        ...CSS_IN_JS.map((name) => ({
          name,
          message: message(
            3,
            `${name}: no CSS-in-JS or class utilities; styling lives only in design-system CSS Modules.`,
          ),
        })),
        ...LAYER_BANS[layer],
        CHART_LIBRARY,
        OVERLAY_LIBRARY,
      ],
      patterns: [STYLE_IMPORTS, DEEP_UI],
    },
  ];
}

/** One config object per app layer with its complete restriction lists. */
export const appRestrictions = Object.keys(LAYER_BANS).map((layer) => ({
  name: `algotrade/restrictions/${layer}`,
  files: [`src/${layer}/**/*.{ts,tsx}`],
  rules: {
    'no-restricted-syntax': [
      'error',
      ...COMPONENT_ONLY,
      ...STYLING_VALUES,
      ...(layer === 'shared/api' ? [] : HTTP_SYNTAX),
    ],
    'no-restricted-imports': restrictedImports(layer),
    'no-restricted-globals': [
      'error',
      ...(layer === 'shared/api'
        ? []
        : ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource']
      ).map((name) => ({
        name,
        message: message(4, `${name}: only src/shared/api talks HTTP.`, PAGE_SKILL),
      })),
    ],
  },
}));

/** Design-system import bans; `chart` = the Chart folder, the one place lightweight-charts is allowed. */
function designSystemImports({ chart }) {
  return [
    'error',
    {
      paths: [
        ...http(HTTP_LIBRARIES),
        ...CSS_IN_JS.map((name) => ({
          name,
          message: message(
            3,
            `${name}: the design system styles with CSS Modules and tokens only.`,
          ),
        })),
        ROUTER,
        QUERY,
        ...(chart ? [] : [CHART_LIBRARY]),
      ],
      patterns: [
        {
          group: ['@/*', '**/src/**'],
          message: message(1, 'the design system never imports app code (src/).'),
        },
      ],
    },
  ];
}

const CHART_FOLDER = 'design-system/components/Chart/**/*.{ts,tsx}';

/** The design system: owns styling and HTML, but never talks HTTP or imports app code. */
export const designSystemRestrictions = {
  name: 'algotrade/restrictions/design-system',
  files: ['design-system/**/*.{ts,tsx}'],
  ignores: [CHART_FOLDER],
  rules: {
    'no-restricted-syntax': ['error', ...HTTP_SYNTAX],
    'no-restricted-imports': designSystemImports({ chart: false }),
  },
};

/** The Chart component: the same rules, plus the one licence to import lightweight-charts. */
export const chartRestrictions = {
  name: 'algotrade/restrictions/design-system-chart',
  files: [CHART_FOLDER],
  rules: {
    'no-restricted-syntax': ['error', ...HTTP_SYNTAX],
    'no-restricted-imports': designSystemImports({ chart: true }),
  },
};
