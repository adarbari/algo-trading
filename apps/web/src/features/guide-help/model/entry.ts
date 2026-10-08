/**
 * A reference to a Guide entry, and the address of its full page. The kinds: `field` (the id is
 * the catalogue name), `indicator` (a regime card's key) and `episode` (a reference market
 * fall's slug); the others (situation, playbook, glossary term) join this union as their drawers
 * ship (docs/ui/guide.md section 4).
 */
import { episodePath, fieldPath, indicatorPath } from '@/entities/guide';

export type GuideEntry =
  | { kind: 'field'; id: string }
  | { kind: 'indicator'; id: string }
  | { kind: 'episode'; id: string };

/** The full page of an entry. */
export function guidePath(entry: GuideEntry): string {
  switch (entry.kind) {
    case 'field':
      return fieldPath(entry.id);
    case 'indicator':
      return indicatorPath(entry.id);
    case 'episode':
      return episodePath(entry.id);
  }
}
