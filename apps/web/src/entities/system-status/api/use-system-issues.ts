/**
 * The open system issues for the viewer: the newest nightly run and the completeness grid only
 * when `admin` (the API refuses them to anyone else), the screeners' run state for everyone. A
 * read that fails or has not arrived adds no issue: the strip reports known problems, never its own loading.
 */
import { useCompleteness } from '@/entities/ingestion';
import { useNightlyRuns } from '@/entities/run';

import { systemIssues, type SystemIssue } from '../model/issues';

import { useScreenerStates } from './queries';

export function useSystemIssues(admin: boolean): SystemIssue[] {
  const nightly = useNightlyRuns(1, admin);
  const completeness = useCompleteness(undefined, admin);
  const screens = useScreenerStates();
  return systemIssues(admin ? nightly.data?.[0] : null, screens.data, completeness.data);
}
