/** The per-module GraphQL documents plugin: same text as codegen, and loud on what it cannot do. */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { rewriteDocuments } from './graphql-documents';

const SRC = join(process.cwd(), 'src');
const GENERATED = readFileSync(join(SRC, 'shared/api/generated/graphql/graphql.ts'), 'utf8');

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (path.includes('/generated')) return [];
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

const flat = (text: string): string => text.replace(/[\s,]+/g, '');

/** The generated document text of `<Name>Document`, whitespace-normalised. */
function generated(name: string): string {
  const start = GENERATED.indexOf(`export const ${name}Document = new TypedDocumentString(\``);
  if (start < 0) return '';
  const open = GENERATED.indexOf('`', start);
  return flat(GENERATED.slice(open + 1, GENERATED.indexOf('`', open + 1)));
}

describe('rewriteDocuments', () => {
  it('inlines every operation with the text codegen generated', () => {
    let count = 0;
    for (const file of sources(SRC)) {
      const code = readFileSync(file, 'utf8');
      const out = rewriteDocuments(code, file);
      if (out === null) continue;
      for (const m of out.matchAll(/new __TypedDocumentString\((`[^`]*`)\)/g)) {
        const literal = m[1] ?? '';
        const op = /(?:query|mutation|subscription)\s+(\w+)/.exec(literal)?.[1] ?? '';
        const op1 = op.charAt(0).toUpperCase() + op.slice(1);
        expect(flat(literal).slice(1, -1), `${file} ${op}`).toBe(generated(op1));
        count += 1;
      }
      expect(out).not.toMatch(/\bgraphql\(\s*`/);
    }
    expect(count).toBeGreaterThan(50);
  });

  it('leaves a module without a graphql() call alone, and ignores comment mentions', () => {
    expect(rewriteDocuments('const a = 1;', 'a.ts')).toBeNull();
    expect(rewriteDocuments('/** the `graphql()` tag */\nconst a = 1;', 'a.ts')).toBeNull();
  });

  it('appends the import, so lines do not shift', () => {
    const out = rewriteDocuments('const Q = graphql(`query Q { a }`);\n', 'a.ts') ?? '';
    expect(
      out.startsWith('const Q = /*#__PURE__*/ new __TypedDocumentString(`query Q { a }`);'),
    ).toBe(true);
    expect(out).toContain('import { TypedDocumentString as __TypedDocumentString }');
  });

  it('throws on a fragment spread or definition, naming file and operation', () => {
    expect(() => rewriteDocuments('const Q = graphql(`query Q { a { ...F } }`);', 'a.ts')).toThrow(
      /a\.ts:1: operation Q uses a fragment/,
    );
    expect(() => rewriteDocuments('const F = graphql(`fragment F on A { b }`);', 'a.ts')).toThrow(
      /uses a fragment/,
    );
  });

  it('throws on a call it cannot rewrite, with file and line', () => {
    expect(() => rewriteDocuments('\n\nconst Q = graphql(`query Q { ${x} }`);', 'a.ts')).toThrow(
      /a\.ts:3: graphql\(\) literal has/,
    );
    expect(() => rewriteDocuments('const Q = graphql(source);', 'a.ts')).toThrow(
      /a\.ts:1: graphql\(\) needs a plain template literal/,
    );
  });
});
