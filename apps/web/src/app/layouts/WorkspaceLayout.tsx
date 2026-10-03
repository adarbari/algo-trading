/**
 * A workspace's layout route: the horizontal top bar (product, workspace switch, the
 * workspace's sections) above the page. Placeholder rendering with primitives only: the real
 * TopBar, WorkspaceSwitch and NavLink are design-system components (design system PR 2), then
 * composed here.
 */
import { Box, Mono, Stack, Surface, Text } from '@algotrade/ui';
import { Outlet } from '@tanstack/react-router';

import { WORKSPACES, type Workspace } from '../workspaces';

export function WorkspaceLayout({ workspace }: { workspace: Workspace }) {
  return (
    <Stack gap={0}>
      <Surface as="header" border="bottom" radius="none" paddingX={5} paddingY={2.5}>
        <Stack direction="row" align="center" gap={4} wrap>
          <Mono weight="medium">algotrade</Mono>
          <Stack direction="row" gap={2} aria-label="Workspace">
            {WORKSPACES.map((w) => (
              <Text
                key={w.id}
                weight="medium"
                tone={w.id === workspace.id ? 'default' : 'secondary'}
              >
                {w.label}
              </Text>
            ))}
          </Stack>
          <Stack as="nav" direction="row" gap={4} aria-label={`${workspace.label} sections`}>
            {workspace.sections.map((s) => (
              <Text key={s.path} tone="secondary">
                {s.label}
              </Text>
            ))}
          </Stack>
        </Stack>
      </Surface>
      <Box as="main" width="page" paddingX={6} paddingY={5}>
        <Stack gap={4}>
          <Outlet />
        </Stack>
      </Box>
    </Stack>
  );
}
