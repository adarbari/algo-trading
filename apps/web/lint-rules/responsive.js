/**
 * Rule 9 (ADR 0025): a multi-column Grid in app code collapses on narrow screens. A `<Grid>`
 * outside design-system/ whose `columns` is not 1 (an omitted `columns` is 2) must pass
 * `collapse="sm" | "md" | "lg"`, so a phone never gets two cramped columns. A list beside its
 * detail is `MasterDetail` instead (a sheet on narrow). The design system's own Grid use is
 * out of scope: its components carry their own container queries.
 */
import { message } from './guide.js';

const RESPONSIVE_SKILL = '.claude/skills/responsive-ui';

const MESSAGE = message(
  9,
  'a multi-column Grid collapses on narrow screens: pass collapse="md" or "lg" (or use MasterDetail for a list beside its detail).',
  RESPONSIVE_SKILL,
);

function attribute(node, name) {
  return node.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === name);
}

/** True for `columns={1}` and `columns="1"`; an absent prop is the default of 2. */
function isSingleColumn(attr) {
  if (!attr?.value) return false;
  const value = attr.value.type === 'JSXExpressionContainer' ? attr.value.expression : attr.value;
  return value.type === 'Literal' && (value.value === 1 || value.value === '1');
}

/** True for `collapse="none"`: present but not collapsing. */
function isNoCollapse(attr) {
  const value = attr?.value;
  return value?.type === 'Literal' && value.value === 'none';
}

export const gridCollapses = {
  meta: {
    type: 'problem',
    docs: { description: 'rule 9: a multi-column Grid collapses on narrow screens' },
    schema: [],
    messages: { collapse: MESSAGE },
  },
  create(context) {
    return {
      JSXOpeningElement(node) {
        if (node.name.type !== 'JSXIdentifier' || node.name.name !== 'Grid') return;
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
