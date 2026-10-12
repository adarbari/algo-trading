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
  toCriterion,
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
import { errorDetail, type components } from '@/shared/api';
import { useDebounced } from '@/shared/lib';

import { useCopyOwnPreset, useDiscardDraft, useSaveDraft } from '../api/hooks';

/** What the trader decided about one thing Describe it offered (ADR 0066), sent with the save. */
export type DraftChoice = components['schemas']['DraftChoice'];
/** A proposed formula: not yet decided, accepted or skipped. */
export type FormulaState = 'proposed' | 'accepted' | 'skipped';
type Formula = components['schemas']['DraftFormula'];

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
  /** Replace the working document with one drafted elsewhere (a sentence, ADR 0041): an unsaved edit. */
  loadDocument: (document: Readonly<Record<string, unknown>>) => void;
  /**
   * The Describe-it feedback session of this screen (ADR 0066): the id of the last draft the
   * model returned, sent with the next sentence and with the save; null for a hand-built screen,
   * and after the screen was finalised or discarded, or another screener opened.
   */
  draftSessionId: string | null;
  setDraftSessionId: (draftSessionId: string | null) => void;
  /**
   * The decisions made on the last answer's options (a reading picked, a formula accepted or
   * skipped), sent with the save and the finalise and cleared with the session. One per event and
   * subject: deciding again replaces it.
   */
  choices: readonly DraftChoice[];
  recordChoice: (choice: DraftChoice) => void;
  /** Each proposed formula's state by name; a name not listed is `proposed`. */
  formulaStates: Readonly<Record<string, FormulaState>>;
  /**
   * The formulas the last answer proposed and the trader has neither accepted nor skipped: each
   * shows as a pending row (when it has a criterion), and finalising waits until none is left.
   */
  pendingFormulas: readonly Formula[];
  /** The formula whose review dialog is open (Review and add), else null. */
  reviewing: Formula | null;
  /** The trader chose Review and add: open the review of that formula. */
  reviewFormula: (formula: Formula) => void;
  /** The review dialog was closed without saving. */
  closeReview: () => void;
  /**
   * The formula was saved as the trader's feature (`field`, `feature.<name>`): its pending
   * criterion joins the screen as an active row on that field, the formula is accepted and
   * `formula_accepted` is recorded. All one edit.
   */
  acceptFormula: (formula: Formula, field: string) => void;
  /** The trader chose Skip: the pending row goes and `formula_skipped` is recorded. */
  skipFormula: (name: string) => void;
  /** A new answer replaced the proposals: none is decided yet. */
  setFormulas: (formulas: readonly Formula[]) => void;
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
      return { id, extends: `${asPreset.presetId}${pin}` };
    }
    return null;
  }, [draft, latest, asPreset, id]);
  const waiting = detail.isPending || (!hasDraft && hasVersions && versions.isPending);
  // No such screen (and no preset of that id) is a null detail: the page says so.
  const missing = detail.data === null ? new Error(`There is no screener ${id}.`) : null;
  const failed = detail.isError
    ? detail.error
    : (missing ?? (versions.isError ? versions.error : null));
  return { detail, source, waiting, failed, hasDraft, hasVersions, asPreset };
}

export function ScreenerBuilderProvider({ id, children }: { id: string; children: ReactNode }) {
  const { detail, source, waiting, failed, hasDraft, asPreset } = useSource(id);
  const [edited, setEdited] = useState<ScreenDocument | null>(null);
  // Keyed by screener, so opening another one starts without a session.
  const [session, setSession] = useState<{ id: string; draftSessionId: string } | null>(null);
  const draftSessionId = session?.id === id ? session.draftSessionId : null;
  // The options' decisions, keyed by screener like the session; gone with it.
  const [review, setReview] = useState<{
    id: string;
    choices: DraftChoice[];
    formulas: Record<string, FormulaState>;
    proposed: readonly Formula[];
    reviewing: string | null;
  } | null>(null);
  const empty: NonNullable<typeof review> = {
    id,
    choices: [],
    formulas: {},
    proposed: [],
    reviewing: null,
  };
  const current = review?.id === id ? review : empty;
  const updateReview = (change: (r: NonNullable<typeof review>) => NonNullable<typeof review>) => {
    setReview((prev) => change(prev?.id === id ? prev : empty));
  };
  const choose = (choice: DraftChoice) => {
    updateReview((r) => ({
      ...r,
      choices: [
        ...r.choices.filter((c) => !(c.event === choice.event && c.subject === choice.subject)),
        choice,
      ],
    }));
  };
  const save = useSaveDraft(id);
  const discard = useDiscardDraft(id);
  const copy = useCopyOwnPreset(id);
  // The copy in flight, so a save or discard waits for it (it makes the draft they write to).
  const copying = useRef<Promise<unknown> | null>(null);

  const base = detail.data?.working ?? null;
  const preset = asPreset ? { id: asPreset.presetId, version: asPreset.current } : null;
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
    if (edited)
      await save.mutateAsync({ document: edited, draftSessionId, choices: current.choices });
    setEdited(null);
  };

  const value: ScreenerBuilder = {
    id,
    status: failed ? 'error' : waiting ? 'loading' : 'ready',
    error: failed ?? null,
    retry: () => void detail.refetch(),
    detail: detail.data ?? undefined,
    preset,
    document,
    criteria,
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
    loadDocument: (next) => {
      edit(toDocument(next, id));
    },
    draftSessionId,
    setDraftSessionId: (next) => {
      setSession(next ? { id, draftSessionId: next } : null);
      if (!next) setReview(null); // the session is over: so are its decisions
    },
    choices: current.choices,
    recordChoice: choose,
    formulaStates: current.formulas,
    pendingFormulas: current.proposed.filter((f) => current.formulas[f.name] === undefined),
    reviewing: current.proposed.find((f) => f.name === current.reviewing) ?? null,
    reviewFormula: (formula) => {
      updateReview((r) => ({ ...r, reviewing: formula.name }));
    },
    closeReview: () => {
      updateReview((r) => ({ ...r, reviewing: null }));
    },
    acceptFormula: (formula, field) => {
      if (formula.criterion) {
        const created = newCriterionId(criterionIds(base, document), field);
        edit(withCriterion(document, toCriterion(created, { ...formula.criterion, field })));
      }
      updateReview((r) => ({
        ...r,
        reviewing: null,
        formulas: { ...r.formulas, [formula.name]: 'accepted' },
      }));
      choose({ event: 'formula_accepted', subject: formula.name });
    },
    skipFormula: (name) => {
      updateReview((r) => ({
        ...r,
        reviewing: r.reviewing === name ? null : r.reviewing,
        formulas: { ...r.formulas, [name]: 'skipped' },
      }));
      choose({ event: 'formula_skipped', subject: name });
    },
    setFormulas: (formulas) => {
      updateReview((r) => ({ ...r, formulas: {}, proposed: formulas, reviewing: null }));
    },
    save: saved,
    discard: async () => {
      await copying.current;
      if (hasDraft || copying.current !== null) await discard.mutateAsync();
      copying.current = null;
      copy.reset();
      setEdited(null);
      setSession(null); // a discarded screen is abandoned: a later description is a new session
      setReview(null);
    },
    saving: save.isPending,
    discarding: discard.isPending,
  };
  return <Context value={value}>{children}</Context>;
}
