/**
 * Admin › Users: the people the site declares, with their role and licences, and the form that onboards a
 * trader. The page only lays them out.
 */
import { Heading, Stack } from '@algotrade/ui';

import { OnboardUserForm } from '@/widgets/user-onboard';
import { UserList } from '@/widgets/user-list';

export function AdminUsersPage() {
  return (
    <Stack gap={4}>
      <Heading level={1}>Users</Heading>
      <OnboardUserForm />
      <UserList />
    </Stack>
  );
}
