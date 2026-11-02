/**
 * The information architecture: two workspaces, each a set of sections reached from the
 * horizontal top bar. TRADER is the default; ADMIN runs the data and the platform. Each
 * section is one route and one page (route groups in src/app/routes/<workspace>/).
 */
export type WorkspaceId = 'trader' | 'admin';

export interface Section {
  /** URL path of the section's route. */
  readonly path: string;
  readonly label: string;
}

export interface Workspace {
  readonly id: WorkspaceId;
  readonly label: string;
  readonly sections: readonly Section[];
}

export const TRADER: Workspace = {
  id: 'trader',
  label: 'Trader',
  sections: [
    {
      path: '/ideas',
      label: 'Ideas',
    },
    {
      path: '/edges',
      label: 'Setups',
    },
    {
      // The Test flow (V9): /screeners and the old builder URLs redirect here.
      path: '/test',
      label: 'Test',
    },
    {
      path: '/calendar',
      label: 'Calendar',
    },
  ],
};

export const ADMIN: Workspace = {
  id: 'admin',
  label: 'Admin',
  sections: [
    {
      path: '/admin/ingestion',
      label: 'Ingestion',
    },
    {
      path: '/admin/llm-usage',
      label: 'LLM usage',
    },
    {
      path: '/admin/harness-runs',
      label: 'Edge runs',
    },
    {
      path: '/admin/feature-requests',
      label: 'Feature requests',
    },
    {
      path: '/admin/screener-runs',
      label: 'Screener runs',
    },
    {
      path: '/admin/users',
      label: 'Users & configs',
    },
  ],
};

export const WORKSPACES: readonly Workspace[] = [TRADER, ADMIN];

export const DEFAULT_WORKSPACE: Workspace = TRADER;

/** The section declared for `path`, or an error (a route must exist for every section). */
export function section(workspace: Workspace, path: string): Section {
  const found = workspace.sections.find((s) => s.path === path);
  if (!found) throw new Error(`${workspace.id}: no section ${path}`);
  return found;
}
