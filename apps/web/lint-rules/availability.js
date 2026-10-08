/**
 * Rule 11 (ADR 0025, ADR 0056): why something is not available is read in one place. The
 * `cause` chain of a gap and the `code` of an `Unknown` are read only inside
 * `src/entities/availability`, which draws them by the gap's public `kind`; everywhere else a
 * page passes the served `unknown` / `unavailable` to `UnknownNote`, `UnavailableNote` or
 * `unknownText`. The server decides who may see a cause (admins only); a page that reads or
 * branches on these fields would filter by role or by code in the browser.
 *
 * Found by name: a `.cause` or `.code` read off something called `unknown`, `unknownReason`,
 * `notRun`, `gap` or `unavailable`, and any `.cause.links`.
 */
import { message } from './guide.js';

const SKILL = '.claude/skills/add-web-page';
const HOME = 'src/entities/availability/**';

const MESSAGE = message(
  11,
  "a gap's `cause` and an Unknown's `code` are read only in entities/availability: render a gap with UnknownNote / UnavailableNote / unknownText (by kind) and never check the role.",
  SKILL,
);

const GAPS = new Set(['unknown', 'unknownReason', 'notRun', 'gap', 'gaps', 'unavailable']);

/** The last name of `a.b.c`, `a?.b` or `a`: what the thing read from is called. */
function lastName(node) {
  if (node.type === 'ChainExpression') return lastName(node.expression);
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'MemberExpression' && !node.computed && node.property.type === 'Identifier') {
    return node.property.name;
  }
  return null;
}

const readsAGap = {
  meta: {
    type: 'problem',
    docs: { description: 'rule 11: a gap is read only in entities/availability' },
    schema: [],
    messages: { gap: MESSAGE },
  },
  create(context) {
    return {
      MemberExpression(node) {
        if (node.computed || node.property.type !== 'Identifier') return;
        const property = node.property.name;
        const from = lastName(node.object);
        if (property === 'links' && from === 'cause') {
          context.report({ node, messageId: 'gap' });
        } else if ((property === 'cause' || property === 'code') && GAPS.has(from)) {
          context.report({ node, messageId: 'gap' });
        }
      },
    };
  },
};

export const availability = {
  name: 'algotrade/availability',
  files: ['src/**/*.{ts,tsx}'],
  ignores: [HOME, 'src/**/*.test.{ts,tsx}', 'src/shared/api/generated/**'],
  plugins: { 'algotrade-availability': { rules: { 'reads-a-gap': readsAGap } } },
  rules: { 'algotrade-availability/reads-a-gap': 'error' },
};

export { readsAGap };
