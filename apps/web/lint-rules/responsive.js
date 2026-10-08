/**
 * Rule 10 (ADR 0025): a multi-column Grid in app code collapses on narrow screens. A `<Grid>`
 * outside design-system/ whose `columns` is not 1 (an omitted `columns` is 2) must pass
 * `collapse="sm" | "md" | "lg"`, so a phone never gets two cramped columns. A list beside its
 * detail is `MasterDetail` instead (a sheet on narrow). The design system's own Grid use is
 * out of scope: its components carry their own container queries. The Grid is found through
 * the file's `@algotrade/ui` import (an alias counts; a namespace import's `.Grid` too); a
 * spread prop may carry `collapse`, so an element with a spread is not reported.
 */
import { message } from './guide.js';

const RESPONSIVE_SKILL = '.claude/skills/responsive-ui';
const UI_PACKAGE = '@algotrade/ui';

const MESSAGE = message(
  10,
  'a multi-column Grid collapses on narrow screens: pass collapse="md" or "lg" (or use MasterDetail for a list beside its detail).',
  RESPONSIVE_SKILL,
);

function attribute(node, name) {
  return node.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === name);
}

/** The literal behind `prop="x"` or `prop={'x'}`; null for anything else. */
function literal(attr) {
  if (!attr?.value) return null;
  const value = attr.value.type === 'JSXExpressionContainer' ? attr.value.expression : attr.value;
  return value.type === 'Literal' ? value.value : null;
}

/** True for `columns={1}` and `columns="1"`; an absent prop is the default of 2. */
function isSingleColumn(attr) {
  const value = literal(attr);
  return value === 1 || value === '1';
}

/** True for `collapse="none"`: present but not collapsing. */
function isNoCollapse(attr) {
  return literal(attr) === 'none';
}

/** The local names that mean the design system's Grid in this file (and its namespace imports). */
function gridNames(program) {
  const locals = new Set();
  const namespaces = new Set();
  for (const statement of program.body) {
    if (statement.type !== 'ImportDeclaration' || statement.source.value !== UI_PACKAGE) continue;
    for (const spec of statement.specifiers) {
      if (spec.type === 'ImportSpecifier' && spec.imported.name === 'Grid') {
        locals.add(spec.local.name);
      } else if (spec.type === 'ImportNamespaceSpecifier') {
        namespaces.add(spec.local.name);
      }
    }
  }
  return { locals, namespaces };
}

function isGrid(name, { locals, namespaces }) {
  if (name.type === 'JSXIdentifier') return locals.has(name.name);
  return (
    name.type === 'JSXMemberExpression' &&
    name.object.type === 'JSXIdentifier' &&
    namespaces.has(name.object.name) &&
    name.property.name === 'Grid'
  );
}

export const gridCollapses = {
  meta: {
    type: 'problem',
    docs: { description: 'rule 10: a multi-column Grid collapses on narrow screens' },
    schema: [],
    messages: { collapse: MESSAGE },
  },
  create(context) {
    let names = { locals: new Set(), namespaces: new Set() };
    return {
      Program(node) {
        names = gridNames(node);
      },
      JSXOpeningElement(node) {
        if (!isGrid(node.name, names)) return;
        if (node.attributes.some((a) => a.type === 'JSXSpreadAttribute')) return;
        if (isSingleColumn(attribute(node, 'columns'))) return;
        const collapse = attribute(node, 'collapse');
        if (collapse && !isNoCollapse(collapse)) return;
        context.report({ node, messageId: 'collapse' });
      },
    };
  },
};

export const responsive = {
  name: 'algotrade/responsive',
  files: ['src/**/*.{ts,tsx}'],
  plugins: { 'algotrade-responsive': { rules: { 'grid-collapses': gridCollapses } } },
  rules: { 'algotrade-responsive/grid-collapses': 'error' },
};
