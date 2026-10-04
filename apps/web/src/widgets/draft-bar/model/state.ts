/** The Builder's state as the header says it: DRAFT vN, unsaved changes, or the finalised version. Pure. */

export interface DraftState {
  label: string;
  tone: 'neutral' | 'accent' | 'warning' | 'positive';
}

export function draftState(builder: {
  preset: unknown;
  dirty: boolean;
  nextVersion: number;
  detail: { draft?: unknown; latest: number | null } | undefined;
}): DraftState {
  if (builder.preset && !builder.dirty) return { label: 'Site preset', tone: 'neutral' };
  const draft = `DRAFT v${String(builder.nextVersion)}`;
  if (builder.dirty) return { label: `${draft} · unsaved changes`, tone: 'warning' };
  if (builder.detail?.draft) return { label: draft, tone: 'accent' };
  return { label: `v${String(builder.detail?.latest ?? 1)} · finalized`, tone: 'positive' };
}
