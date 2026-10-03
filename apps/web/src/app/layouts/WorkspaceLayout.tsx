/**
 * A workspace's layout route: the app shell with the horizontal top bar (product, workspace
 * switch, the workspace's sections) above the page. Composition only: AppShell, TopBar,
 * WorkspaceSwitch and NavTabs come from the design system; this file supplies the router's
 * current path, its Link and navigation (the design system knows no routes).
 */
import { AppShell, Mono, NavTabs, TopBar, WorkspaceSwitch } from '@algotrade/ui';
import { Link, Outlet, useNavigate, useRouterState } from '@tanstack/react-router';

import { WORKSPACES, type Workspace, type WorkspaceId } from '../workspaces';

const WORKSPACE_OPTIONS = WORKSPACES.map((w) => ({ value: w.id, label: w.label }));

export function WorkspaceLayout({ workspace }: { workspace: Workspace }) {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const navigate = useNavigate();
  const enter = (id: WorkspaceId) => {
    const home = WORKSPACES.find((w) => w.id === id)?.sections[0]?.path;
    if (home) void navigate({ to: home });
  };
  return (
    <AppShell
      topBar={
        <TopBar
          brand={<Mono weight="medium">algotrade</Mono>}
          workspace={
            <WorkspaceSwitch
              workspaces={WORKSPACE_OPTIONS}
              value={workspace.id}
              onValueChange={enter}
            />
          }
          nav={
            <NavTabs
              aria-label={`${workspace.label} sections`}
              items={workspace.sections.map((s) => ({ href: s.path, label: s.label }))}
              activeHref={pathname}
              renderLink={({ href, ...link }) => <Link to={href} {...link} />}
            />
          }
        />
      }
    >
      <Outlet />
    </AppShell>
  );
}
