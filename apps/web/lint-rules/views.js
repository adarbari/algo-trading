/**
 * Read model WEB 7 (docs/api/read-model.md "Enforcement"): one adapter for a user's views of a
 * table. Only src/features/table-view/api names the preferences path (`/preferences/...`):
 * every table reads and saves its view through `useTableView(scope)`, never a REST call of its
 * own.
 */
import { readModelMessage } from './guide.js';

const ADAPTER = 'src/features/table-view/api/**';

const ALLOWED = [];

const PATH = /\/preferences\//;

const MESSAGE = readModelMessage(
  7,
  "a table's saved view goes through the one adapter, features/table-view (useTableView(scope), ViewControls): only its api/ names /preferences/.",
);

/** Reports a string or template literal naming `/preferences/` outside the adapter. */
const oneViewAdapter = {
  meta: {
    type: 'problem',
    docs: { description: 'read model WEB 7: one view-preferences adapter' },
    schema: [],
    messages: { path: MESSAGE },
  },
  create(context) {
    const check = (node, text) => {
      if (typeof text === 'string' && PATH.test(text)) context.report({ node, messageId: 'path' });
    };
    return {
      Literal(node) {
        check(node, node.value);
      },
      TemplateElement(node) {
        check(node, node.value.raw);
      },
    };
  },
};

export const viewAdapter = {
  name: 'algotrade/read-model/view-adapter',
  files: ['src/**/*.{ts,tsx}'],
  ignores: [ADAPTER, ...ALLOWED, 'src/**/*.test.{ts,tsx}', 'src/shared/api/generated/**'],
  plugins: { 'algotrade-views': { rules: { 'view-adapter': oneViewAdapter } } },
  rules: { 'algotrade-views/view-adapter': 'error' },
};
