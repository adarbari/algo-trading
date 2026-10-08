/**
 * The Guide's layout: the top bar of the workspace the user came from, so an admin who opens
 * the Guide stays in ADMIN (its sections in the nav, Admin checked in the account menu), a trader stays in
 * TRADER, and with no earlier workspace it is the default one.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Text, UiProvider } from '@algotrade/ui';

import { currentSession, gql, subscribeSession } from '@/shared/api';

import { ADMIN, rememberWorkspace, TRADER } from '../workspaces';
import { GuideLayout } from './GuideLayout';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    gql: vi.fn(),
    currentSession: vi.fn(),
    subscribeSession: vi.fn(() => () => undefined),
  };
});

const ADMIN_VIEWER = { id: 'bo', name: 'Bo', role: 'admin', workspaces: ['trader', 'admin'] };

beforeEach(() => {
  vi.mocked(currentSession).mockResolvedValue(null);
  vi.mocked(subscribeSession).mockReturnValue(() => undefined);
  vi.mocked(gql).mockResolvedValue({ viewer: ADMIN_VIEWER });
});

function setup() {
  const root = createRootRoute({ component: GuideLayout });
  const guide = createRoute({
    getParentRoute: () => root,
    path: '/guide',
    component: () => <Text>guide page</Text>,
  });
  const router = createRouter({
    routeTree: root.addChildren([guide]),
    history: createMemoryHistory({ initialEntries: ['/guide'] }),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <UiProvider>
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </UiProvider>,
  );
}

describe('GuideLayout', () => {
  it('keeps an admin in ADMIN: the switch on Admin and its sections in the nav', async () => {
    rememberWorkspace(ADMIN);
    setup();
    expect(await screen.findByText('guide page')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Ingestion' })).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Ideas' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^Guide/ })).toHaveAttribute('aria-current');
    await userEvent.click(await screen.findByRole('button', { name: 'Bo' }));
    expect(await screen.findByRole('radio', { name: 'Admin' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('keeps a user who came from TRADER in TRADER', async () => {
    rememberWorkspace(TRADER);
    setup();
    expect(await screen.findByRole('link', { name: 'Ideas' })).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Ingestion' })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Bo' }));
    expect(await screen.findByRole('radio', { name: 'Trader' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });
});
