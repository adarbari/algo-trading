/**
 * A reference to a Guide entry, and the address of its full page. Only `field` exists today;
 * the other kinds (situation, regime indicator, playbook, glossary term) join this union as
 * their pages ship (docs/ui/guide.md section 4).
 */

export type GuideEntry = { kind: 'field'; id: string };

/** The full page of an entry (`/guide/fields/<catalogue name>`). */
export function guidePath(entry: GuideEntry): string {
  return `/guide/fields/${encodeURIComponent(entry.id)}`;
}
