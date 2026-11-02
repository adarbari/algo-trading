/**
 * Admin › Users: the people the site declares, with their role and licences. The page only lays
 * the widget out.
 */
import { Heading, Stack } from '@algotrade/ui';

import { UserList } from '@/widgets/user-list';

export function AdminUsersPage() {
  return (
    <Stack gap={4}>
      <Heading level={1}>Users</Heading>
      <UserList />
    </Stack>
  );
}
