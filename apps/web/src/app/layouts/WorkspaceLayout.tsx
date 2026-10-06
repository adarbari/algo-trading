/**
 * A workspace's layout route: the app shell with the horizontal top bar (product, workspace
 * switch, the workspace's sections) above the page. Composition only: AppShell, TopBar,
 * WorkspaceSwitch and NavTabs come from the design system; this file supplies the router's
 * current path, its Link and navigation (the design system knows no routes). The switch lists
 * only the workspaces the viewer may enter; the end slot shows their name and, when they signed
 * in through Supabase, a sign-out action. A viewer that turns null (the API refused the token)
 * goes back to the login page.
 */
import {
  AppShell,
  Button,
  Mono,
  NavTabs,
  Stack,
  Text,
  TopBar,
  WorkspaceSwitch,
} from '@algotrade/ui';
import { Link, Outlet, useNavigate, useRouterState } from '@tanstack/react-router';
import { useEffect } from 'react';

import { useSession, useSignOut, useViewer } from '@/entities/viewer';

import { canEnter, WORKSPACES, type Workspace, type WorkspaceId } from '../workspaces';

/** The section a path belongs to (`/screeners/new` is in `/screeners`), else the path itself. */
const activeSection = (workspace: Workspace, pathname: string): string =>
  workspace.sections.find((s) => pathname === s.path || pathname.startsWith(`${s.path}/`))?.path ??
  pathname;

export function WorkspaceLayout({ workspace }: { workspace: Workspace }) {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const navigate = useNavigate();
  const viewer = useViewer().data;
  const { session } = useSession();
  const signOut = useSignOut();
  useEffect(() => {
    if (viewer === null) void navigate({ to: '/login', search: {} });
  }, [viewer, navigate]);
  const options = WORKSPACES.filter((w) => canEnter(viewer ?? null, w.id)).map((w) => ({
    value: w.id,
    label: w.label,
  }));
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
            <WorkspaceSwitch workspaces={options} value={workspace.id} onValueChange={enter} />
          }
          end={
            viewer && (
              <Stack direction="row" gap={2} align="center">
                <Text size="sm">{viewer.name}</Text>
                {session && (
                  <Button variant="ghost" size="sm" onClick={() => void signOut()}>
                    Sign out
                  </Button>
                )}
              </Stack>
            )
          }
          nav={
            <NavTabs
              aria-label={`${workspace.label} sections`}
              items={workspace.sections.map((s) => ({ href: s.path, label: s.label }))}
              activeHref={activeSection(workspace, pathname)}
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
