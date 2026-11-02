/** `/admin/users`: the Admin › Users page. */
import { createRoute, type AnyRoute } from '@tanstack/react-router';

import { lazyPage } from '@/shared/lib/lazy';

import { pageRoute } from '../page-loader';

const AdminUsersPage = lazyPage(() => import('@/pages/admin-users'), 'AdminUsersPage');

export function usersRoute<P extends AnyRoute>(parent: P) {
  return createRoute({
    getParentRoute: () => parent,
    path: 'users',
    ...pageRoute(AdminUsersPage),
    component: AdminUsersPage,
  });
}
