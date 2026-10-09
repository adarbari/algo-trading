/**
 * The open system issues for the viewer: the newest nightly run and the completeness grid only
 * when `admin` (the API refuses them to anyone else), the screeners' run state for everyone.
 * The grid is one session wide: the strip reads only its latest stored and last closed
 * sessions, and ten sessions cost the API 5 s on every page. One operation reads all of it. A
 * read that fails or has not arrived adds no issue: the strip reports known problems, never its own loading.
 */
import { systemIssues, type SystemIssue } from '../model/issues';

import { useStatusStrip } from './queries';

export function useSystemIssues(admin: boolean): SystemIssue[] {
  const { data } = useStatusStrip(admin);
  return systemIssues(data?.nightly, data?.screens, data?.completeness);
}
