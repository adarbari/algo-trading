/**
 * The top bar of a workspace layout for each kind of viewer: the regime chip opens the Regime
 * page, the Guide link (and the "?" key) opens the Guide for everyone, the switch lists only the
 * workspaces the registry role allows, the name shows, sign-out appears only with a Supabase
 * session, and a viewer that turns null goes back to the login page.
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

import { SearchInput, Text, UiProvider } from '@algotrade/ui';

import { currentSession, gql, signOutSession, subscribeSession } from '@/shared/api';

import { TRADER } from '../workspaces';
import { WorkspaceLayout } from './WorkspaceLayout';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    gql: vi.fn(),
    currentSession: vi.fn(),
    subscribeSession: vi.fn(() => () => undefined),
    signOutSession: vi.fn(() => Promise.resolve()),
  };
});

const TRADER_VIEWER = { id: 'ann', name: 'Ann', role: 'trader', workspaces: ['trader'] };
const ADMIN_VIEWER = { id: 'bo', name: 'Bo', role: 'admin', workspaces: ['trader', 'admin'] };

beforeEach(() => {
  vi.mocked(currentSession).mockResolvedValue(null);
  vi.mocked(subscribeSession).mockReturnValue(() => undefined);
});

function setup() {
  const root = createRootRoute({ component: () => <WorkspaceLayout workspace={TRADER} /> });
  const ideas = createRoute({
    getParentRoute: () => root,
    path: '/ideas',
    component: () => <SearchInput aria-label="Test field" />,
  });
  const regime = createRoute({
    getParentRoute: () => root,
    path: '/regime',
    component: () => <Text>regime page</Text>,
  });
  const guide = createRoute({
    getParentRoute: () => root,
    path: '/guide',
    component: () => <Text>guide page</Text>,
  });
  const login = createRoute({
    getParentRoute: () => root,
    path: '/login',
    component: () => <Text>login page</Text>,
  });
  const router = createRouter({
    routeTree: root.addChildren([ideas, regime, guide, login]),
    history: createMemoryHistory({ initialEntries: ['/ideas'] }),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <UiProvider>
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </UiProvider>,
  );
  return { router };
}

describe('WorkspaceLayout top bar', () => {
  it('shows an admin their name, and both workspaces in the account menu', async () => {
    vi.mocked(gql).mockResolvedValue({ viewer: ADMIN_VIEWER });
    setup();
    expect(screen.queryByRole('radio', { name: 'Admin' })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Bo' }));
    expect(await screen.findByRole('radio', { name: 'Trader' })).toBeVisible();
    expect(screen.getByRole('radio', { name: 'Admin' })).toBeVisible();
  });

  it('shows the regime chip beside the name and opens the Regime page', async () => {
    // The mocked API answers every operation with the viewer: `regime` is missing, so not computed.
    vi.mocked(gql).mockResolvedValue({ viewer: TRADER_VIEWER });
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Regime: not computed' }));
    expect(await screen.findByText('regime page')).toBeVisible();
  });

  it('shows the Guide link to every viewer, before the name, and opens the Guide', async () => {
    vi.mocked(gql).mockResolvedValue({ viewer: TRADER_VIEWER });
    setup();
    const link = await screen.findByRole('link', { name: /Guide/ });
    expect(link).toHaveAttribute('href', '/guide');
    expect(link.compareDocumentPosition(screen.getByText('Ann'))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    await userEvent.click(link);
    expect(await screen.findByText('guide page')).toBeVisible();
  });

  it('opens the Guide on "?" unless the focus is in a text field', async () => {
    vi.mocked(gql).mockResolvedValue({ viewer: ADMIN_VIEWER });
    const { router } = setup();
    await screen.findByText('Bo');
    await userEvent.click(screen.getByRole('searchbox', { name: 'Test field' }));
    await userEvent.keyboard('?');
    expect(router.state.location.pathname).toBe('/ideas');
    expect(screen.getByRole('searchbox', { name: 'Test field' })).toHaveValue('?');
    await userEvent.click(document.body);
    await userEvent.keyboard('?');
    expect(await screen.findByText('guide page')).toBeVisible();
  });

  it('offers a trader no workspace switch at all', async () => {
    vi.mocked(gql).mockResolvedValue({ viewer: TRADER_VIEWER });
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Ann' }));
    expect(await screen.findByText('Signed in as Ann')).toBeVisible();
    expect(screen.queryByRole('radio', { name: 'Trader' })).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Admin' })).not.toBeInTheDocument();
  });

  it('offers no sign-out without a Supabase session (the API runs with auth off)', async () => {
    vi.mocked(gql).mockResolvedValue({ viewer: ADMIN_VIEWER });
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Bo' }));
    await screen.findByText('Signed in as Bo');
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument();
  });

  it('signs out from the account menu and goes to the login page', async () => {
    vi.mocked(gql).mockResolvedValue({ viewer: TRADER_VIEWER });
    vi.mocked(currentSession).mockResolvedValue({ email: 'ann@example.com' });
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Ann' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(signOutSession).toHaveBeenCalledTimes(1);
    expect(await screen.findByText('login page')).toBeVisible();
  });
});
