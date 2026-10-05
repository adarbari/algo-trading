/**
 * A screener run on request (POST /screens/{id}/run): `ready` (results for this version and
 * session are already stored), or the job's state `queued`, `running`, `complete`, `partial`
 * (finished with missing data) or `failed`. Pure.
 */
import type { components } from '@/shared/api';

export type ScreenRun = components['schemas']['RunRequest'];

/** Still going: poll it. */
export const isActive = (run: ScreenRun | undefined): boolean =>
  run?.state === 'queued' || run?.state === 'running';

/** What to tell the user about a run, in a few words. */
export function runMessage(run: ScreenRun | undefined): string | null {
  if (!run) return null;
  switch (run.state) {
    case 'queued':
    case 'running':
      return `Running for ${run.session}…`;
    case 'ready':
      return `Already up to date for ${run.session}`;
    case 'complete':
      return `Updated for ${run.session}`;
    case 'partial':
      return `Updated for ${run.session}, with some data missing`;
    default:
      return run.error ? `The run failed: ${run.error}` : 'The run failed';
  }
}
