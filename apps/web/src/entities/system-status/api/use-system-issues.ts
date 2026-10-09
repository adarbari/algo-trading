/**
 * The open system issues for the viewer: the newest nightly run only when `admin` (the API
 * refuses it to anyone else), the screeners' run state for everyone. A read that fails or has
 * not arrived adds no issue: the strip reports known problems, never its own loading.
 */
import { useNightlyRuns } from '@/entities/run';

import { systemIssues, type SystemIssue } from '../model/issues';

import { useScreenerStates } from './queries';

export function useSystemIssues(admin: boolean): SystemIssue[] {
  const nightly = useNightlyRuns(1, admin);
  const screens = useScreenerStates();
  return systemIssues(admin ? nightly.data?.[0] : null, screens.data);
}
