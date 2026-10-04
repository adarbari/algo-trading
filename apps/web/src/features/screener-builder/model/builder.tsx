/**
 * The Builder's state, shared by the page's widgets through a provider: the screen's server
 * state (draft, versions, preset pin), the working document with its unsaved edits, the
 * criteria, the 300 ms debounced live preview, and the draft actions (save, discard).
 */
import { createContext, useContext, useMemo, useRef, useState, type ReactNode } from 'react';

import {
  criteriaOf,
  criterionOfError,
  criterionIds,
  newCriterionId,
  previewDocument,
  tieBreakOf,
  toDocument,
  useScreener,
  useScreenerVersions,
  useScreenPreview,
  withCriterion,
  withoutCriterion,
  withTieBreak,
  type Criterion,
  type ScreenDocument,
  type ScreenerDetail,
  type ScreenPreview,
} from '@/entities/screen';
import { errorDetail } from '@/shared/api';
import { useDebounced } from '@/shared/lib';

import { useCopyOwnPreset, useDiscardDraft, useSaveDraft } from '../api/hooks';

/** The live preview waits this long after the last edit. */
export const PREVIEW_DEBOUNCE_MS = 300;

export interface PreviewState {
  data: ScreenPreview | undefined;
  /** Waiting for the debounce or the API. */
  pending: boolean;
  /** The API's message when the draft would not run (names the criterion). */
  error: string | null;
  /** Nothing to preview yet: no complete criterion. */
  idle: boolean;
}

export interface ScreenerBuilder {
  id: string;
  status: 'loading' | 'error' | 'ready';
  error: Error | null;
  retry: () => void;
  detail: ScreenerDetail | undefined;
  /**
   * A site preset the user has not copied yet: shown with its live preview; the first edit makes
   * their copy (a draft pinned to its version) and carries on in it.
   */
  preset: { id: string; version: number | null } | null;
  document: ScreenDocument;
  criteria: Criterion[];
  /** The universe (named selection) the screen runs over, if known. */
  selection: string | null;
  dirty: boolean;
  /** The newest version: finalising saves version `nextVersion`. */
  nextVersion: number;
  tieBreak: { field: string | null; order: 'asc' | 'desc' };
  /** The criterion the preview's error names, if any. */
  errorCriterion: string | null;
  preview: PreviewState;
  setCriterion: (criterion: Criterion) => void;
  removeCriterion: (id: string) => void;
  /** A blank criterion row; returns its id. */
  addCriterion: (field?: string) => string;
  setTieBreak: (field: string | null, order: 'asc' | 'desc') => void;
  save: () => Promise<void>;
  discard: () => Promise<void>;
  saving: boolean;
  discarding: boolean;
}

const Context = createContext<ScreenerBuilder | null>(null);

export function useScreenerBuilder(): ScreenerBuilder {
  const builder = useContext(Context);
  if (!builder) throw new Error('useScreenerBuilder needs a ScreenerBuilderProvider');
  return builder;
}

/** The named universe: the draft's own `selection`, else the resolved config's. */
function selectionOf(
  document: ScreenDocument,
  resolved: Readonly<Record<string, unknown>> | null | undefined,
): string | null {
  if (typeof document['selection'] === 'string') return document['selection'];
  const selection = resolved?.['selection'] as { name?: unknown } | null | undefined;
  return typeof selection?.name === 'string' ? selection.name : null;
}

/** The server's working document: the draft, else the latest version, else (a preset) a copy of it. */
function useSource(id: string) {
  const detail = useScreener(id);
  const hasDraft = Boolean(detail.data?.draft);
  const hasVersions = (detail.data?.versions.length ?? 0) > 0;
  const versions = useScreenerVersions(id, Boolean(detail.data) && !hasDraft && hasVersions);
  const draft = detail.data?.draft;
  const latest = hasVersions ? versions.data?.at(-1) : undefined;
  const untouched = detail.data?.preset ?? null;
  const asPreset = !draft && !hasVersions && untouched ? untouched : null;
  const source = useMemo<ScreenDocument | null>(() => {
    if (draft) return toDocument(draft, id);
    if (latest) return toDocument(latest.document, id);
    if (asPreset) {
      const pin = asPreset.current === null ? '' : `@${String(asPreset.current)}`;
      return { id, extends: `${asPreset.preset_id}${pin}` };
    }
    return null;
  }, [draft, latest, asPreset, id]);
  const waiting = detail.isPending || (!hasDraft && hasVersions && versions.isPending);
  const failed = detail.isError ? detail.error : versions.isError ? versions.error : null;
  return { detail, source, waiting, failed, hasDraft, hasVersions, asPreset };
}

export function ScreenerBuilderProvider({ id, children }: { id: string; children: ReactNode }) {
  const { detail, source, waiting, failed, hasDraft, asPreset } = useSource(id);
  const [edited, setEdited] = useState<ScreenDocument | null>(null);
  const save = useSaveDraft(id);
  const discard = useDiscardDraft(id);
  const copy = useCopyOwnPreset(id);
  // The copy in flight, so a save or discard waits for it (it makes the draft they write to).
  const copying = useRef<Promise<unknown> | null>(null);

  const base = detail.data?.working ?? null;
  const preset = asPreset ? { id: asPreset.preset_id, version: asPreset.current } : null;
  const document = useMemo<ScreenDocument>(() => edited ?? source ?? { id }, [edited, source, id]);
  const criteria = useMemo(() => criteriaOf(base, document), [base, document]);

  const spec = useMemo(() => previewDocument(document), [document]);
  const runnable = criteriaOf(base, spec).some((c) => c.field !== '');
  // Edits wait out the debounce; a freshly loaded or saved draft previews at once.
  const live = useDebounced(spec, PREVIEW_DEBOUNCE_MS, edited === null);
  const preview = useScreenPreview(runnable ? live : null);
  const previewError = preview.isError ? errorDetail(preview.error) : null;
  const settled = live === spec;

  const edit = (next: ScreenDocument) => {
    setEdited(next);
    if (preset && copying.current === null) {
      copying.current = copy.mutateAsync().catch(() => {
        // The toast says why; the edit is dropped so the next one tries again.
        copying.current = null;
        setEdited(null);
      });
    }
  };
  const saved = async () => {
    await copying.current;
    if (edited) await save.mutateAsync(edited);
    setEdited(null);
  };

  const value: ScreenerBuilder = {
    id,
    status: failed ? 'error' : waiting ? 'loading' : 'ready',
    error: failed ?? null,
    retry: () => void detail.refetch(),
    detail: detail.data,
    preset,
    document,
    criteria,
    selection: selectionOf(document, detail.data?.resolved),
    dirty: edited !== null,
    nextVersion: (detail.data?.latest ?? 0) + 1,
    tieBreak: tieBreakOf(base, document),
    errorCriterion: criterionOfError(previewError),
    preview: {
      data: preview.data,
      pending: !settled || preview.isFetching,
      error: previewError,
      idle: !runnable,
    },
    setCriterion: (criterion) => {
      edit(withCriterion(document, criterion));
    },
    removeCriterion: (criterionId) => {
      edit(withoutCriterion(document, base, criterionId));
    },
    addCriterion: (field = '') => {
      const created = newCriterionId(criterionIds(base, document), field);
      edit(withCriterion(document, { id: created, field, op: 'gte', mode: 'hard' }));
      return created;
    },
    setTieBreak: (field, order) => {
      edit(withTieBreak(document, field, order));
    },
    save: saved,
    discard: async () => {
      await copying.current;
      if (hasDraft || copying.current !== null) await discard.mutateAsync();
      copying.current = null;
      copy.reset();
      setEdited(null);
    },
    saving: save.isPending,
    discarding: discard.isPending,
  };
  return <Context value={value}>{children}</Context>;
}
