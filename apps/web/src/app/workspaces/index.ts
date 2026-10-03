/** Workspaces (TRADER, ADMIN), their sections and the role-gating seam. */
export { canEnter, workspaceGuard } from './guard';
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
