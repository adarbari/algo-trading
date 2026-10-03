/**
 * The workspace guard: the one seam for role gating. Every workspace layout route runs it in
 * `beforeLoad`. Today the app is local and single-user, so every workspace is open; when users
 * and roles arrive (ADR 0015), `canEnter` reads them and ADMIN is restricted here, nowhere else.
 */
import { redirect } from '@tanstack/react-router';

import { DEFAULT_WORKSPACE, type WorkspaceId } from './workspaces';

/** Whether the current user may enter a workspace (always true until roles exist). */
export function canEnter(_workspace: WorkspaceId): boolean {
  return true;
}

/** `beforeLoad` for a workspace's layout route: redirect to the default workspace if refused. */
export function workspaceGuard(workspace: WorkspaceId): () => void {
  return () => {
    if (!canEnter(workspace)) {
      // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
      throw redirect({ to: DEFAULT_WORKSPACE.sections[0]?.path ?? '/' });
    }
  };
}
