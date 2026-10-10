/**
 * The builder's one draft (ADR 0053 amendment, ED8): every setting the six steps edit, started
 * from the edge being built (its served settings) or blank, and assembled back into the WHOLE
 * edge document for `PUT /edges/{id}` (the save replaces the document: never a diff, and keys the
 * builder does not edit stay as the user's own file has them). Pure; the server decides what is
 * valid and says so.
 */
import type { Edge } from '@/entities/edge';

import type { EdgeSettings } from '../api/settings';
import { isIsoDate } from './date';

/** New edge, a copy of a site (or the user's own) edge, or a new version of a followed edge. */
export type Mode = 'new' | 'clone' | 'version';
export type Schedule = 'every_session' | 'month_end' | 'on_event';
export type Win = 'beats' | 'rises' | 'other';

/** The seven quality-bar answers besides mechanism and persistence, in the document's order. */
export const QUALITY_KEYS = [
  'outcome',
  'trigger_timing',
  'replication',
  'expected_size',
  'capacity_costs',
  'failure_modes',
  'decoys',
] as const;

export interface SourceDraft {
  title: string;
  url: string;
}

export interface EdgeDraft {
  /** The id of a new edge (a clone or version has its own already). */
  id: string;
  name: string;
  thesis: string;
  mechanism: string;
  persistence: string;
  sources: SourceDraft[];
  qualityBar: Record<string, string>;
  screeners: string[];
  schedule: Schedule;
  event: string;
  take: 'top' | 'all';
  topK: number | null;
  startOffset: number | null;
  horizons: number[];
  costBps: number | null;
  win: Win;
  universe: string;
  baselines: string[];
  /** The out-of-sample start, yyyy-mm-dd; empty: none. */
  frozenFrom: string;
}

export const DEFAULT_EVENT = 'earnings_reaction';
const ON_EVENT = 'on_event:';

/** A new edge's draft: every choice the form needs has a value, the prose is empty. */
export function blankDraft(): EdgeDraft {
  return {
    id: '',
    name: '',
    thesis: '',
    mechanism: '',
    persistence: '',
    sources: [{ title: '', url: '' }],
    qualityBar: Object.fromEntries(QUALITY_KEYS.map((k) => [k, ''])),
    screeners: [],
    schedule: 'every_session',
    event: DEFAULT_EVENT,
    take: 'top',
    topK: 20,
    startOffset: 1,
    horizons: [20],
    costBps: 15,
    win: 'beats',
    universe: '',
    baselines: [],
    frozenFrom: '',
  };
}

/** The draft of an existing edge: what the server resolved, nothing derived. */
export function draftOf(
  edge: Pick<Edge, 'id' | 'name' | 'thesis' | 'mechanism' | 'persistence' | 'sources'> &
    Pick<Edge, 'screeners' | 'baselines' | 'horizons'>,
  served: EdgeSettings,
): EdgeDraft {
  const settings = served.settings;
  const blank = blankDraft();
  const event = served.schedule.startsWith(ON_EVENT) ? served.schedule.slice(ON_EVENT.length) : '';
  const schedule: Schedule = event
    ? 'on_event'
    : served.schedule === 'month_end'
      ? 'month_end'
      : 'every_session';
  const answers = new Map((settings?.qualityBar ?? []).map((a) => [a.key, a.text]));
  return {
    ...blank,
    id: edge.id,
    name: edge.name,
    thesis: edge.thesis,
    mechanism: edge.mechanism,
    persistence: edge.persistence,
    sources: edge.sources.length
      ? edge.sources.map((s) => ({ title: s.title, url: s.url }))
      : blank.sources,
    qualityBar: Object.fromEntries(QUALITY_KEYS.map((k) => [k, answers.get(k) ?? ''])),
    screeners: [...edge.screeners],
    schedule,
    event: event || DEFAULT_EVENT,
    take: settings?.topK === null ? 'all' : 'top',
    topK: settings?.topK ?? blank.topK,
    startOffset: settings?.startOffsetSessions ?? blank.startOffset,
    horizons: [...edge.horizons],
    costBps: settings?.costBps ?? null,
    win:
      settings?.kind !== 'excess_return'
        ? 'other'
        : settings.benchmark === 'none'
          ? 'rises'
          : 'beats',
    universe: settings?.universe ?? '',
    baselines: [...edge.baselines],
    frozenFrom: served.frozenFrom ?? '',
  };
}

const trimmed = (text: string) => text.trim();

/**
 * The whole document to save. `own` is the user's own document as the server has it (`{}` for a
 * new edge): its keys the builder does not edit (variants, notes, a scorer, outcome extras) are
 * kept as they are, and `extends` stays. A copy carries every setting the builder shows, so the
 * file says what the user chose even when the site edge changes later.
 */
export function toDocument(
  draft: EdgeDraft,
  own: Record<string, unknown>,
  extendsId: string | null,
): Record<string, unknown> {
  const doc: Record<string, unknown> = { ...own, id: draft.id };
  if (extendsId !== null) doc.extends = extendsId;
  doc.name = trimmed(draft.name);
  doc.thesis = trimmed(draft.thesis);
  doc.mechanism = trimmed(draft.mechanism);
  doc.persistence = trimmed(draft.persistence);
  doc.sources = draft.sources
    .filter((s) => trimmed(s.title) !== '')
    .map((s) =>
      trimmed(s.url)
        ? { title: trimmed(s.title), url: trimmed(s.url) }
        : { title: trimmed(s.title) },
    );
  doc.quality_bar = {
    ...(own.quality_bar as Record<string, unknown> | undefined),
    ...Object.fromEntries(QUALITY_KEYS.map((k) => [k, trimmed(draft.qualityBar[k] ?? '')])),
  };
  doc.schedule = draft.schedule === 'on_event' ? `${ON_EVENT}${draft.event}` : draft.schedule;
  doc.top_k = draft.take === 'all' ? 'all' : draft.topK;
  doc.screeners = draft.screeners;
  doc.baselines = draft.baselines;
  if (draft.universe) doc.universe = draft.universe;
  const outcome: Record<string, unknown> = {
    ...(own.outcome as Record<string, unknown> | undefined),
    horizon_sessions: draft.horizons,
  };
  if (draft.startOffset !== null) outcome.start_offset_sessions = draft.startOffset;
  if (draft.costBps !== null) outcome.cost_bps = draft.costBps;
  if (draft.win !== 'other') {
    outcome.kind = 'excess_return';
    outcome.benchmark = draft.win === 'beats' ? 'SPY' : 'none';
  }
  doc.outcome = outcome;
  if (draft.frozenFrom) doc.frozen_from = draft.frozenFrom;
  else delete doc.frozen_from;
  delete doc.follow; // the state has its own call
  return doc;
}

const ID = /^[a-z0-9_-]{1,64}$/;

/** A new edge's id: 1-64 of a-z, 0-9, _ and - (the API's rule). */
export const isEdgeId = (id: string): boolean => ID.test(id);

export const STEPS = ['idea', 'screens', 'picks', 'trade', 'compare', 'test'] as const;
export type Step = (typeof STEPS)[number];

/** The steps that block saving, in order (empty: the draft can be saved). */
export function incomplete(draft: EdgeDraft, mode: Mode): Step[] {
  const blank = (...texts: string[]) => texts.some((t) => trimmed(t) === '');
  const found: Step[] = [];
  const answers =
    blank(draft.name, draft.thesis, draft.mechanism, draft.persistence) ||
    QUALITY_KEYS.some((k) => trimmed(draft.qualityBar[k] ?? '') === '') ||
    !draft.sources.some((s) => trimmed(s.title) !== '');
  if ((mode === 'new' && !isEdgeId(draft.id)) || answers) found.push('idea');
  if (draft.screeners.length === 0) found.push('screens');
  if (draft.take === 'top' && (draft.topK === null || draft.topK < 1)) found.push('picks');
  if (draft.horizons.length === 0 || draft.startOffset === null || draft.startOffset < 1) {
    found.push('trade');
  }
  if (draft.universe === '' && mode === 'new') found.push('compare');
  if (draft.frozenFrom !== '' && !isIsoDate(draft.frozenFrom)) found.push('test');
  return found;
}

/** Whether `draft` differs from `initial` (so leaving asks, and Save is worth pressing). */
export const isDirty = (draft: EdgeDraft, initial: EdgeDraft): boolean =>
  JSON.stringify(draft) !== JSON.stringify(initial);
