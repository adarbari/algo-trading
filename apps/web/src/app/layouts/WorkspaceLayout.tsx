/**
 * A workspace's layout route: the app shell with the horizontal top bar (product, the
 * workspace's sections, the Guide, the regime chip and the account menu) above the page.
 * Composition only: AppShell, TopBar, AccountMenu, WorkspaceSwitch and NavTabs come from the
 * design system; this file supplies the router's current path, its Link and navigation (the
 * design system knows no routes). The account menu (the viewer's name) holds the workspace
 * switch, listing only the workspaces the viewer may enter (hidden when there is one), and,
 * when they signed in through Supabase, a sign-out action; the regime chip (ADR 0047) sits
 * before the name, on both workspaces, and opens the Regime page. The status strip (open system
 * issues, ADR 0052's one tree) sits under the bar on every page once the viewer is known. The Guide's search dialog
 * (Ctrl+K / ⌘K) is mounted here once, for every page of both workspaces and the Guide. A viewer that turns null (the
 * API refused the token) goes back to the login page.
 */
import {
  AccountMenu,
  AppShell,
  LinkProvider,
  Mono,
  NavTabs,
  Stack,
  Text,
  TextLink,
  TopBar,
  WorkspaceSwitch,
} from '@algotrade/ui';
import { Link, Outlet, useNavigate, useRouter, useRouterState } from '@tanstack/react-router';
import { useEffect } from 'react';

import { RegimeChip } from '@/entities/regime';
import { useSession, useSignOut, useViewer } from '@/entities/viewer';
import { GuideSearchProvider } from '@/features/guide-search';
import { SystemStatusStrip } from '@/widgets/status-strip';

import {
  canEnter,
  rememberWorkspace,
  WORKSPACES,
  type Workspace,
  type WorkspaceId,
} from '../workspaces';

import { renderRouterLink } from './router-link';
import { useGuideShortcut } from './use-guide-shortcut';

/** The section a path belongs to (`/screeners/new` is in `/screeners`), else the path itself. */
const activeSection = (workspace: Workspace, pathname: string): string =>
  workspace.sections.find((s) => pathname === s.path || pathname.startsWith(`${s.path}/`))?.path ??
  pathname;

export function WorkspaceLayout({ workspace }: { workspace: Workspace }) {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const navigate = useNavigate();
  const router = useRouter();
  const viewer = useViewer().data;
  const { session } = useSession();
  const signOut = useSignOut();
  useGuideShortcut();
  useEffect(() => {
    rememberWorkspace(workspace);
  }, [workspace]);
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
    <LinkProvider render={renderRouterLink}>
      <GuideSearchProvider
        navigate={(path) => {
          router.history.push(path);
        }}
      >
        <AppShell
          strip={viewer ? <SystemStatusStrip admin={canEnter(viewer, 'admin')} /> : null}
          topBar={
            <TopBar
              brand={<Mono weight="medium">algotrade</Mono>}
              utility={
                <TextLink
                  href="/guide"
                  icon="book"
                  keys={['?']}
                  current={pathname === '/guide' || pathname.startsWith('/guide/')}
                >
                  Guide
                </TextLink>
              }
              end={
                viewer && (
                  <Stack direction="row" gap={2} align="center">
                    <RegimeChip onOpen={() => void navigate({ to: '/regime' })} />
                    <AccountMenu
                      name={viewer.name}
                      {...(session ? { onSignOut: () => void signOut() } : {})}
                    >
                      {options.length > 1 ? (
                        <Stack gap={1}>
                          <Text size="xs" tone="muted">
                            Workspace
                          </Text>
                          <WorkspaceSwitch
                            workspaces={options}
                            value={workspace.id}
                            onValueChange={enter}
                          />
                        </Stack>
                      ) : null}
                    </AccountMenu>
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
      </GuideSearchProvider>
    </LinkProvider>
  );
}
