/**
 * The session notice of every page (ADR 0062): the newer session left out and why, from the
 * status strip's one read (the same query as the issues, so no extra request). Null while it
 * loads or when the served session is the newest.
 */
import type { SessionNotice } from '../model/notice';

import { useStatusStrip } from './queries';

export function useSessionNotice(admin: boolean): SessionNotice | null {
  const { data } = useStatusStrip(admin);
  return data?.notice ?? null;
}
