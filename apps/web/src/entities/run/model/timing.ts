/** Run timing: a nightly run's steps by duration (longest first) with their share of the run. */
import type { NightlyRun } from './types';

export interface StepTiming {
  name: string;
  status: string;
  durationS: number;
  /** Of the steps' total duration, 0..1. */
  share: number;
}

export function stepTimings(run: NightlyRun): StepTiming[] {
  const steps = run.steps.filter((s) => s.duration_s !== null);
  const total = steps.reduce((sum, s) => sum + (s.duration_s ?? 0), 0);
  return steps
    .map((s) => ({
      name: s.name,
      status: s.status,
      durationS: s.duration_s ?? 0,
      share: total > 0 ? (s.duration_s ?? 0) / total : 0,
    }))
    .sort((a, b) => b.durationS - a.durationS || a.name.localeCompare(b.name));
}

// A step that is done: SUCCEEDED (ADR 0039) or COMPLETE in records written before it.
const DONE = new Set(['COMPLETE', 'SUCCEEDED']);

/** Steps that did not complete (not SUCCEEDED / COMPLETE), in recorded order. */
export function incompleteSteps(run: NightlyRun): string[] {
  return run.steps.filter((s) => !DONE.has(s.status.toUpperCase())).map((s) => s.name);
}
