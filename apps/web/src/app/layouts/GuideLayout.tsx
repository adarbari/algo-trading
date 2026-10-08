/**
 * The Guide's layout route: the same top bar as a workspace, in the workspace the user came from
 * (the Guide belongs to neither, and every role may open it), so opening it from ADMIN keeps
 * ADMIN. The switch still moves between workspaces.
 */
import { lastWorkspace } from '../workspaces';

import { WorkspaceLayout } from './WorkspaceLayout';

export function GuideLayout() {
  return <WorkspaceLayout workspace={lastWorkspace()} />;
}
