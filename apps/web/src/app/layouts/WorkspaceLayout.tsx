/**
 * A workspace's layout route: the horizontal top bar (product, workspace switch, the
 * workspace's sections) above the page. Placeholder rendering with primitives only: the real
 * TopBar, WorkspaceSwitch and NavLink are design-system components built after the mockups
 * are approved (ADR 0011), then composed here.
 */
import { Stack, Text } from '@algotrade/ui';
import { Outlet } from '@tanstack/react-router';

import { WORKSPACES, type Workspace } from '../workspaces';

export function WorkspaceLayout({ workspace }: { workspace: Workspace }) {
  return (
    <Stack gap={0}>
      <Stack as="header" direction="row" align="center" gap={6} padding={3}>
        <Text variant="heading" as="span">
          algotrade
        </Text>
        <Stack direction="row" gap={2} aria-label="Workspace">
          {WORKSPACES.map((w) => (
            <Text key={w.id} variant="label" tone={w.id === workspace.id ? 'accent' : 'muted'}>
              {w.label}
            </Text>
          ))}
        </Stack>
        <Stack as="nav" direction="row" gap={4} aria-label={`${workspace.label} sections`}>
          {workspace.sections.map((s) => (
            <Text key={s.path} variant="label">
              {s.label}
            </Text>
          ))}
        </Stack>
      </Stack>
      <Stack as="main" padding={4} gap={4}>
        <Outlet />
      </Stack>
    </Stack>
  );
}
