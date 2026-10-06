/**
 * The workspace guard: the one seam for role gating (ADR 0040 decision 4). Every workspace
 * layout route runs it in `beforeLoad`: no session sends the user to `/login`, a workspace the
 * viewer's registry role does not include sends them to the default workspace. It only hides:
 * the server enforces the role on every request.
 */
import type { QueryClient } from '@tanstack/react-query';
import { redirect } from '@tanstack/react-router';

import { ensureViewer, type Viewer } from '@/entities/viewer';
import { ApiError } from '@/shared/api';

import { DEFAULT_WORKSPACE, WORKSPACES, type WorkspaceId } from './workspaces';

/** Why `/login` was opened without the user asking (carried in the URL's search). */
export type LoginReason = 'unregistered';

/** Whether the viewer may enter a workspace: the registry lists it in their `workspaces`. */
export function canEnter(viewer: Viewer | null, workspace: WorkspaceId): boolean {
  return viewer?.workspaces.includes(workspace) ?? false;
}

/** The home path of the first workspace the viewer may enter, the default one first. */
export function homeFor(viewer: Viewer | null): string | null {
  const open = [DEFAULT_WORKSPACE, ...WORKSPACES].find((w) => canEnter(viewer, w.id));
  return open?.sections[0]?.path ?? null;
}

/** Redirect to `/login` (with the reason when there is one) or to a workspace home. */
function go(to: string, reason?: LoginReason): never {
  // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
  throw redirect({ to, search: () => (reason ? { reason } : {}) });
}

/** `beforeLoad` for a workspace's layout route. */
export function workspaceGuard(
  workspace: WorkspaceId,
): (args: { context: { queryClient: QueryClient } }) => Promise<void> {
  return async ({ context }) => {
    let viewer: Viewer | null;
    try {
      viewer = await ensureViewer(context.queryClient);
    } catch (error) {
      // A valid token the registry does not know: sign-in again is pointless, say why.
      if (error instanceof ApiError && error.status === 403) {
        return go('/login', 'unregistered');
      }
      throw error;
    }
    if (!viewer) return go('/login');
    if (canEnter(viewer, workspace)) return;
    const home = homeFor(viewer);
    return home === null ? go('/login', 'unregistered') : go(home);
  };
}
