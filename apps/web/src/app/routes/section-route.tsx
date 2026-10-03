/**
 * Builds one section's route under a workspace layout route. Until a section's page is built
 * it renders the generic placeholder page; then the route's component becomes that page
 * (.claude/skills/add-web-page).
 */
import { createRoute, type AnyRoute } from '@tanstack/react-router';

import { PlaceholderPage } from '@/pages/placeholder';

import { section, type Workspace } from '../workspaces';

export function placeholderRoute<P extends AnyRoute>(
  parent: P,
  workspace: Workspace,
  fullPath: string,
  path: string,
) {
  const { label, summary } = section(workspace, fullPath);
  return createRoute({
    getParentRoute: () => parent,
    path,
    component: () => <PlaceholderPage title={label} summary={summary} />,
  });
}
