/**
 * A reference to a Guide entry, and the address of its full page. The kinds: `field` (the id is
 * the catalogue name), `indicator` (a regime card's key) and `episode` (a reference market
 * fall's slug), `term` (a glossary term's id), `start` (a Start here page's id), `mechanism` and
 * `edge` (a mechanism's or a site edge's id in the Edges section); the others
 * (situation, screener) join this union as their drawers ship (docs/ui/guide.md section 4).
 */
import {
  edgeGuidePath,
  episodePath,
  fieldPath,
  indicatorPath,
  mechanismPath,
  startPath,
  termPath,
} from '@/entities/guide';

export type GuideEntry =
  | { kind: 'field'; id: string }
  | { kind: 'indicator'; id: string }
  | { kind: 'episode'; id: string }
  | { kind: 'term'; id: string }
  | { kind: 'start'; id: string }
  | { kind: 'mechanism'; id: string }
  | { kind: 'edge'; id: string };

/** The full page of an entry. */
export function guidePath(entry: GuideEntry): string {
  switch (entry.kind) {
    case 'field':
      return fieldPath(entry.id);
    case 'indicator':
      return indicatorPath(entry.id);
    case 'episode':
      return episodePath(entry.id);
    case 'term':
      return termPath(entry.id);
    case 'start':
      return startPath(entry.id);
    case 'mechanism':
      return mechanismPath(entry.id);
    case 'edge':
      return edgeGuidePath(entry.id);
  }
}
