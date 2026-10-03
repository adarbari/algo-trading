/**
 * Lists the design-system component folders (primitives/<Name>, components/<Name>) and reads
 * their public description and props with the TypeScript compiler. Used by the COMPONENTS.md
 * generator and the design-system completeness check.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';

export const WEB_ROOT = fileURLToPath(new URL('..', import.meta.url));
export const DS_ROOT = join(WEB_ROOT, 'design-system');
export const KINDS = ['primitives', 'components'] as const;
/** Every story is screenshotted and accessibility-checked in both themes. */
export const THEMES = ['light', 'dark'] as const;

/** Screenshot file stem for a story export: `DenseRows` -> `dense-rows`. */
export function storyFileStem(exportName: string): string {
  return exportName.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
}

export interface ComponentFolder {
  kind: (typeof KINDS)[number];
  name: string;
  dir: string;
  /** Path relative to apps/web. */
  rel: string;
}

export function componentFolders(): ComponentFolder[] {
  return KINDS.flatMap((kind) => {
    const root = join(DS_ROOT, kind);
    if (!existsSync(root)) return [];
    return readdirSync(root)
      .filter((name) => statSync(join(root, name)).isDirectory())
      .sort()
      .map((name) => ({
        kind,
        name,
        dir: join(root, name),
        rel: relative(WEB_ROOT, join(root, name)),
      }));
  });
}

export interface PropDoc {
  name: string;
  type: string;
  optional: boolean;
  doc: string;
}

export interface ComponentDoc {
  description: string;
  props: PropDoc[];
}

function jsDoc(node: ts.Node, source: ts.SourceFile): string {
  const ranges = ts.getLeadingCommentRanges(source.text, node.getFullStart()) ?? [];
  const last = ranges.at(-1);
  if (!last) return '';
  const raw = source.text.slice(last.pos, last.end);
  if (!raw.startsWith('/**')) return '';
  return raw
    .replace(/^\/\*\*|\*\/$/g, '')
    .split('\n')
    .map((line) => line.replace(/^\s*\* ?/, '').trim())
    .filter(Boolean)
    .join(' ');
}

/** The file docstring (first JSDoc) and the members of `<Name>Props` declared in `<Name>.tsx`. */
export function readComponentDoc(folder: ComponentFolder): ComponentDoc {
  const file = join(folder.dir, `${folder.name}.tsx`);
  if (!existsSync(file)) return { description: '', props: [] };
  const source = ts.createSourceFile(
    file,
    readFileSync(file, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
  );
  const first = source.statements[0];
  const description = first ? jsDoc(first, source) : '';
  const props: PropDoc[] = [];
  source.forEachChild((node) => {
    if (!ts.isInterfaceDeclaration(node) || node.name.text !== `${folder.name}Props`) return;
    for (const heritage of node.heritageClauses ?? []) {
      for (const type of heritage.types) {
        props.push({
          name: `(${type.getText(source).replace(/\s+/g, ' ')})`,
          type: 'inherited',
          optional: true,
          doc: '',
        });
      }
    }
    for (const member of node.members) {
      if (!ts.isPropertySignature(member)) continue;
      props.push({
        name: member.name.getText(source),
        type: member.type ? member.type.getText(source).replace(/\s+/g, ' ') : 'unknown',
        optional: Boolean(member.questionToken),
        doc: jsDoc(member, source),
      });
    }
  });
  return { description, props };
}
