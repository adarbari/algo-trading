/**
 * Vite plugin: each GraphQL operation ships with the module that writes it. The client preset's
 * `graphql()` looks a document up in a map of every operation (generated gql.ts), which puts all
 * of them in whichever chunk imports it (the entry). The preset's Babel / SWC plugins do not run
 * under Vite 8's oxc transform, so this does the same rewrite: `graphql(`...`)` becomes a pure
 * `new TypedDocumentString(`...`)` of the same text. A call it cannot rewrite, or a document with
 * fragments (codegen appends their definitions; the literal lacks them), fails the build.
 */
import type { Plugin } from 'vite';

const DOCUMENT_CLASS = '@/shared/api/generated/graphql/graphql';
const CALL = /\bgraphql\(\s*/g;
const LITERAL = /^`(?:[^`$]|\$(?!\{))*`\s*\)/;

function lineOf(code: string, index: number): number {
  return code.slice(0, index).split('\n').length;
}

/** The rewritten source, or null when `code` has no `graphql(` call. Throws on an unsupported one. */
export function rewriteDocuments(code: string, id: string): string | null {
  if (!code.includes('graphql(')) return null;
  let out = '';
  let last = 0;
  let found = false;
  for (const call of code.matchAll(CALL)) {
    const start = call.index;
    const literalAt = start + call[0].length;
    // A mention in a comment (`graphql()` in prose) is not a call.
    const linePrefix = code.slice(code.lastIndexOf('\n', start) + 1, start);
    if (/^\s*(\*|\/\/|\/\*)/.test(linePrefix) || code[literalAt] === ')') continue;
    if (code[literalAt] !== '`') {
      throw new Error(
        `${id}:${String(lineOf(code, start))}: graphql() needs a plain template literal`,
      );
    }
    const rest = code.slice(literalAt);
    const m = LITERAL.exec(rest);
    if (!m) {
      throw new Error(
        `${id}:${String(lineOf(code, start))}: graphql() literal has \${} or is not closed; write a plain template`,
      );
    }
    const literal = m[0].slice(0, m[0].lastIndexOf('`') + 1);
    // An inline fragment (`... on Type`) carries its own selection; only a named one is a gap.
    if (/\.\.\.\s*(?!on\b)[A-Za-z_]|(^|[\s`])fragment\s+\w+\s+on\b/.test(literal)) {
      const name = /(query|mutation|subscription)\s+(\w+)/.exec(literal)?.[2] ?? 'anonymous';
      throw new Error(
        `${id}:${String(lineOf(code, start))}: operation ${name} uses a fragment; codegen appends its definition, which an inlined literal lacks`,
      );
    }
    out += `${code.slice(last, start)}/*#__PURE__*/ new __TypedDocumentString(${literal})`;
    last = literalAt + m[0].length;
    found = true;
  }
  if (!found) return null;
  // Appended, not prepended, so the lines of the module (and its source map) do not shift.
  return `${out}${code.slice(last)}\nimport { TypedDocumentString as __TypedDocumentString } from ${JSON.stringify(DOCUMENT_CLASS)};\n`;
}

export function perModuleDocuments(): Plugin {
  return {
    name: 'algotrade:graphql-per-module-documents',
    enforce: 'pre',
    transform(code, id) {
      if (
        !/\.tsx?$/.test(id) ||
        id.includes('/generated/') ||
        id.includes('/vite-plugins/') ||
        id.includes('node_modules')
      ) {
        return null;
      }
      const result = rewriteDocuments(code, id);
      return result === null ? null : { code: result, map: null };
    },
  };
}
