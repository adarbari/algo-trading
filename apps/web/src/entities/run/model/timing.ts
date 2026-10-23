/** Run timing: a nightly run's steps by duration (longest first) with their share of the run. */
import type { NightlyRun } from './types';

export interface StepTiming {
  name: string;
  status: string;
  /** What the step took in this attempt (a reused step: 0, it did no work now). */
  durationS: number;
  /** Of this attempt's work, 0..1 (0 for a reused step). */
  share: number;
  /** The earlier attempt that did a reused step (null: it ran in this attempt). */
  origin: string | null;
  /** When that attempt started (null: not reused, or its record is gone). */
  originStartedAt: string | null;
  /** What the step took there (null: not reused, or its record is gone). */
  originDurationS: number | null;
}

/** Whether the attempt reused the step from an earlier attempt instead of running it. */
export const isReused = (t: Pick<StepTiming, 'origin'>): boolean => t.origin !== null;

const byLongest = (a: StepTiming, b: StepTiming) =>
  b.durationS - a.durationS || a.name.localeCompare(b.name);
const byOriginLongest = (a: StepTiming, b: StepTiming) =>
  (b.originDurationS ?? 0) - (a.originDurationS ?? 0) || a.name.localeCompare(b.name);

/**
 * The steps of an attempt in one list: those it ran now, longest first with their share of this
 * attempt's work, then those it reused from earlier attempts, longest (there) first.
 */
export function stepTimings(run: NightlyRun): StepTiming[] {
  const steps = run.steps.filter((s) => s.durationS !== null || s.origin != null);
  const timings = steps.map((s): StepTiming => ({
    name: s.name,
    status: s.status,
    durationS: s.origin != null ? 0 : (s.durationS ?? 0),
    share: 0,
    origin: s.origin ?? null,
    originStartedAt: s.originStartedAt ?? null,
    originDurationS: s.originDurationS ?? null,
  }));
  const total = timings.reduce((sum, t) => sum + t.durationS, 0);
  const ran = timings
    .filter((t) => !isReused(t))
    .map((t) => ({ ...t, share: total > 0 ? t.durationS / total : 0 }))
    .sort(byLongest);
  const reused = timings.filter(isReused).sort(byOriginLongest);
  return [...ran, ...reused];
}

// A step that is done: SUCCEEDED (ADR 0039) or COMPLETE in records written before it.
const DONE = new Set(['COMPLETE', 'SUCCEEDED']);

/** Steps that did not complete (not SUCCEEDED / COMPLETE), in recorded order. */
export function incompleteSteps(run: NightlyRun): string[] {
  return run.steps.filter((s) => !DONE.has(s.status.toUpperCase())).map((s) => s.name);
}
