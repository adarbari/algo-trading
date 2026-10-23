/**
 * Run timing: a nightly run's steps in one list, each in one of five states, with what it
 * needs and what it holds back (the edges the attempt recorded) for the highlight.
 */
import type { NightlyRun } from './types';

/** Ran now, reused from an earlier attempt, waiting on its source, held by an upstream step, failed. */
export type StepState = 'ran' | 'reused' | 'waiting' | 'held' | 'failed';

export interface StepTiming {
  name: string;
  status: string;
  state: StepState;
  /** What the step took in this attempt (a reused or held step: 0, it did no work now). */
  durationS: number;
  /** Of this attempt's work, 0..1 (0 for a reused or held step). */
  share: number;
  /** The earlier attempt that did a reused step (null: it ran in this attempt). */
  origin: string | null;
  /** What a reused step took in the attempt that did it (null: not reused, or its record is gone). */
  originDurationS: number | null;
  /** When the step itself began (UTC ISO; a reused step: in the attempt that did it). */
  startedAt: string | null;
  /** The steps it waits for (null: the run was recorded before edges were). */
  needs: readonly string[] | null;
  /** Steps whose success in the same attempt re-runs it. */
  rerunsAfter: readonly string[];
  reason: string | null;
  error: string | null;
}

/** Whether the attempt reused the step from an earlier attempt instead of running it. */
export const isReused = (t: Pick<StepTiming, 'origin'>): boolean => t.origin !== null;

// A step that is done: SUCCEEDED (ADR 0039) or COMPLETE in records written before it.
const DONE = new Set(['COMPLETE', 'SUCCEEDED']);
const FAILED = new Set(['FAILED', 'PARTIAL', 'BLOCKED']);

function stateOf(status: string, origin: string | null): StepState {
  const s = status.toUpperCase();
  if (FAILED.has(s)) return 'failed';
  if (s === 'WAITING') return 'waiting';
  if (!DONE.has(s)) return 'held';
  return origin === null ? 'ran' : 'reused';
}

const ORDER: Record<StepState, number> = { failed: 0, ran: 1, waiting: 2, reused: 3, held: 4 };

const byOrder = (a: StepTiming, b: StepTiming) =>
  ORDER[a.state] - ORDER[b.state] ||
  (a.state === 'reused' ? (b.originDurationS ?? 0) - (a.originDurationS ?? 0) : 0) ||
  b.durationS - a.durationS ||
  a.name.localeCompare(b.name);

/**
 * The steps of an attempt in one list: failed first, then those it ran now (longest first, with
 * their share of this attempt's work), those waiting on their source, those it reused from
 * earlier attempts (longest there first) and those held by an upstream step.
 */
export function stepTimings(run: NightlyRun): StepTiming[] {
  const timings = run.steps.map((s): StepTiming => {
    const origin = s.origin ?? null;
    const state = stateOf(s.status, origin);
    const worked = state === 'reused' || state === 'held' ? 0 : (s.durationS ?? 0);
    return {
      name: s.name,
      status: s.status,
      state,
      durationS: worked,
      share: 0,
      origin,
      originDurationS: s.originDurationS ?? null,
      startedAt: s.startedAt ?? null,
      needs: s.needs ?? null,
      rerunsAfter: s.rerunsAfter,
      reason: s.reason ?? null,
      error: s.error ?? null,
    };
  });
  const total = timings.reduce((sum, t) => sum + t.durationS, 0);
  return timings.map((t) => ({ ...t, share: total > 0 ? t.durationS / total : 0 })).sort(byOrder);
}

/** How a step stands against the selected one. */
export type Relation = 'selected' | 'upstream' | 'downstream' | 'dimmed';

/**
 * Every step's relation to ``selected``: what it needs (transitively) is upstream, what is held
 * back by it (transitively) is downstream, the rest dimmed. Empty when nothing is selected or
 * the run recorded no edges for it (then every step is shown as it is).
 */
export function relations(timings: readonly StepTiming[], selected: string | null) {
  const out = new Map<string, Relation>();
  const chosen = timings.find((t) => t.name === selected);
  if (!chosen || chosen.needs === null) return out;
  const needs = new Map(timings.map((t) => [t.name, t.needs ?? []]));
  const holds = new Map<string, string[]>();
  for (const t of timings)
    for (const n of t.needs ?? []) holds.set(n, [...(holds.get(n) ?? []), t.name]);
  const reach = (edges: Map<string, readonly string[]>) => {
    const seen = new Set<string>();
    const queue = [...(edges.get(chosen.name) ?? [])];
    for (let name = queue.pop(); name !== undefined; name = queue.pop()) {
      if (seen.has(name)) continue;
      seen.add(name);
      queue.push(...(edges.get(name) ?? []));
    }
    return seen;
  };
  const up = reach(needs);
  const down = reach(holds);
  for (const t of timings) {
    out.set(
      t.name,
      t.name === chosen.name
        ? 'selected'
        : up.has(t.name)
          ? 'upstream'
          : down.has(t.name)
            ? 'downstream'
            : 'dimmed',
    );
  }
  return out;
}

/** The step's direct neighbours: what it needs and what it holds back (in list order). */
export function neighbours(timings: readonly StepTiming[], name: string) {
  const step = timings.find((t) => t.name === name);
  return {
    needs: step?.needs ?? null,
    holds: timings.filter((t) => t.needs?.includes(name) ?? false).map((t) => t.name),
  };
}

/** Steps that did not complete (not SUCCEEDED / COMPLETE), in recorded order. */
export function incompleteSteps(run: NightlyRun): string[] {
  return run.steps.filter((s) => !DONE.has(s.status.toUpperCase())).map((s) => s.name);
}
