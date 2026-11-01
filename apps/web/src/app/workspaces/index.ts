/** Workspaces (TRADER, ADMIN), their sections and the role-gating seam. */
export { canEnter, viewerGuard, workspaceGuard } from './guard';
export { onboardingGuard, ONBOARDING_PATH } from './onboarding';
export { lastWorkspace, rememberWorkspace } from './last-workspace';
export {
  ADMIN,
  DEFAULT_WORKSPACE,
  section,
  TRADER,
  WORKSPACES,
  type Section,
  type Workspace,
  type WorkspaceId,
} from './workspaces';
