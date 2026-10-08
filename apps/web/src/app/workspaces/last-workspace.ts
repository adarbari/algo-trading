/**
 * The workspace the user was last in, so the role-free Guide (which belongs to no workspace)
 * keeps the top bar of the one they came from. Kept in memory, and in sessionStorage (guarded:
 * it can throw or be empty) so a reload of a Guide page keeps it too.
 */
import { DEFAULT_WORKSPACE, WORKSPACES, type Workspace } from './workspaces';

const KEY = 'algotrade.lastWorkspace';
let last: Workspace | null = null;

export function rememberWorkspace(workspace: Workspace): void {
  last = workspace;
  try {
    sessionStorage.setItem(KEY, workspace.id);
  } catch {
    // Storage unavailable: the in-memory value still serves this page load.
  }
}

/** The remembered workspace, else the default one. */
export function lastWorkspace(): Workspace {
  if (last) return last;
  try {
    const id = sessionStorage.getItem(KEY);
    return WORKSPACES.find((w) => w.id === id) ?? DEFAULT_WORKSPACE;
  } catch {
    return DEFAULT_WORKSPACE;
  }
}
