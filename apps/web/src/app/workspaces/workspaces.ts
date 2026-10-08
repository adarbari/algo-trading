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
  /** What the section is for (shown by the placeholder page until it is built). */
  readonly summary: string;
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
      summary:
        "Home: screeners ranked in the user's priority order and a combined ranked list of top ideas.",
    },
    {
      path: '/screeners',
      label: 'Screeners',
      summary:
        'Builder: criteria with hard, soft or score mode, thresholds and tolerances, live preview, save and finalize.',
    },
    {
      path: '/edges',
      label: 'Edges',
      summary:
        'Each edge, a written reason a pattern should last, with its status, frozen period and the odds of its screeners.',
    },
    {
      path: '/explore',
      label: 'Explore',
      summary:
        'One page for universe, instruments, chains and features: a filterable ticker table with columns from the feature catalogue, multi-select compare, and detail tabs (Overview, Chart, Options, Features, Events, Screener hits).',
    },
    {
      path: '/regime',
      label: 'Regime',
      summary:
        'The market as weather: Clear, Clouds building, Storm or Severe storm, the slow and fast warning signs behind it in plain words, what changed this week and a reading list.',
    },
    {
      path: '/calendar',
      label: 'Calendar',
      summary:
        'What is coming across names for the next 90 days: earnings, macro releases and expiry days, for the scope list or the names a screener picked.',
    },
    { path: '/backtests', label: 'Backtests', summary: 'Run backtests and compare their results.' },
  ],
};

export const ADMIN: Workspace = {
  id: 'admin',
  label: 'Admin',
  sections: [
    {
      path: '/admin/ingestion',
      label: 'Ingestion',
      summary:
        'Completeness grid (dataset x session) with drill-down, quality checks and open issues.',
    },
    {
      path: '/admin/llm-usage',
      label: 'LLM usage',
      summary:
        'What the text model spends: tokens and cost against the budget, by model, use case and user, and every recent call.',
    },
    {
      path: '/admin/screener-runs',
      label: 'Screener runs',
      summary: 'Per-user scheduled screens, run history and publishing (sharing) results.',
    },
    {
      path: '/admin/users',
      label: 'Users & configs',
      summary: 'Users and their configs (site presets, user layers).',
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
