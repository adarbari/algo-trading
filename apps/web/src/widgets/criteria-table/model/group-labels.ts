/**
 * What the Builder says about a group's members: an `any` with a score member never rejects
 * (a label; what a group means is the Guide's entries, ADR 0051). Pure.
 */
import type { Criterion, CriterionGroup } from '@/entities/screen';

/** The label of an `any` group that holds a score criterion: one that never rejects (ADR 0071). */
export const NEVER_REJECTS = 'Never rejects';

/** An `any` takes its best member's verdict, so a score member (which never rejects) makes it never reject. */
export function neverRejects(group: CriterionGroup, criteria: readonly Criterion[]): boolean {
  return (
    group.kind === 'any' &&
    group.members.some((id) => criteria.find((c) => c.id === id)?.mode === 'score')
  );
}
