/**
 * An evaluation run on request: the job's state `queued`, `running`, `complete`, `partial`
 * (finished with missing data) or `failed`. Pure.
 */
import type { components } from '@/shared/api';

/** The POST's answer (`EvaluationRequest`) or the job's status (`JobStatus`). */
export type EvaluationRun = Pick<
  components['schemas']['EvaluationRequest'] | components['schemas']['JobStatus'],
  'state' | 'exploratory' | 'error'
>;

/** Still going: poll it. */
export const isActive = (run: EvaluationRun | undefined): boolean =>
  run?.state === 'queued' || run?.state === 'running';

/** What to tell the user about a run, in a few words. */
export function evaluationMessage(run: EvaluationRun | undefined): string | null {
  if (!run) return null;
  switch (run.state) {
    case 'queued':
    case 'running':
      return 'Evaluating…';
    case 'complete':
      return run.exploratory ? 'Done (exploratory)' : 'Done';
    case 'partial':
      return 'Done, with some data missing';
    default:
      return run.error ? `The evaluation failed: ${run.error}` : 'The evaluation failed';
  }
}
