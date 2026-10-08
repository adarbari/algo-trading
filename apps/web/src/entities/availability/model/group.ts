/**
 * One note per kind: the gaps of a response grouped by their public kind, the features under
 * each merged (one table's gap and another's read as one), and the cause chains kept apart
 * (an admin reads one per gap; the server sends none to anyone else).
 */
import { KIND_ORDER } from './kinds';
import type { ServedCause, ServedUnavailable, UnavailableKindName } from './served';

export interface KindGroup {
  kind: UnavailableKindName;
  guideTerm: string;
  features: readonly string[];
  causes: readonly ServedCause[];
}

interface Building {
  guideTerm: string;
  features: Set<string>;
  causes: ServedCause[];
}

export function groupByKind(gaps: readonly ServedUnavailable[]): KindGroup[] {
  const groups = new Map<UnavailableKindName, Building>();
  for (const gap of gaps) {
    const group = groups.get(gap.kind) ?? {
      guideTerm: gap.guideTerm,
      features: new Set<string>(),
      causes: [],
    };
    gap.features.forEach((name) => group.features.add(name));
    if (gap.cause && gap.cause.links.length > 0) group.causes.push(gap.cause);
    groups.set(gap.kind, group);
  }
  return KIND_ORDER.flatMap((kind) => {
    const group = groups.get(kind);
    return group
      ? [{ kind, guideTerm: group.guideTerm, features: [...group.features], causes: group.causes }]
      : [];
  });
}
