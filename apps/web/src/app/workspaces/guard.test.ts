import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Viewer } from '@/entities/viewer';
import { ApiError, gql } from '@/shared/api';

import { canEnter, homeFor, viewerGuard, workspaceGuard } from './guard';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const GQL = vi.mocked(gql);
const TRADER: Viewer = { id: 'ann', name: 'Ann', role: 'trader', workspaces: ['trader'] };
const ADMIN: Viewer = { id: 'bo', name: 'Bo', role: 'admin', workspaces: ['trader', 'admin'] };

let queryClient: QueryClient;
beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

/** What the guard throws (a router redirect), or undefined when it lets the route load. */
async function outcome(workspace: 'trader' | 'admin' | 'any') {
  try {
    const guard = workspace === 'any' ? viewerGuard : workspaceGuard(workspace);
    await guard({ context: { queryClient } });
  } catch (thrown) {
    const { options } = thrown as { options: { to: string; search?: () => unknown } };
    return { to: options.to, search: options.search?.() };
  }
  return undefined;
}

describe('canEnter', () => {
  it('follows the registry role: trader is TRADER only, admin both, nobody none', () => {
    expect(canEnter(TRADER, 'trader')).toBe(true);
    expect(canEnter(TRADER, 'admin')).toBe(false);
    expect(canEnter(ADMIN, 'admin')).toBe(true);
    expect(canEnter(null, 'trader')).toBe(false);
  });

  it('opens on the default workspace, else the first one allowed', () => {
    expect(homeFor(ADMIN)).toBe('/ideas');
    expect(homeFor({ ...TRADER, workspaces: ['admin'] })).toBe('/admin/ingestion');
    expect(homeFor({ ...TRADER, workspaces: [] })).toBeNull();
  });
});

describe('workspaceGuard', () => {
  it('lets an admin into the admin workspace', async () => {
    GQL.mockResolvedValue({ viewer: ADMIN });
    await expect(outcome('admin')).resolves.toBeUndefined();
  });

  it('lets a trader into the trader workspace', async () => {
    GQL.mockResolvedValue({ viewer: TRADER });
    await expect(outcome('trader')).resolves.toBeUndefined();
  });

  it('sends a trader who opens /admin to the default workspace', async () => {
    GQL.mockResolvedValue({ viewer: TRADER });
    await expect(outcome('admin')).resolves.toMatchObject({ to: '/ideas' });
  });

  it('sends no session (401) to the login page', async () => {
    GQL.mockRejectedValue(new ApiError(401, 'Unauthorized'));
    await expect(outcome('trader')).resolves.toEqual({ to: '/login', search: {} });
  });

  it('sends a token the registry does not know (403) to the login page with the reason', async () => {
    GQL.mockRejectedValue(new ApiError(403, 'Forbidden'));
    await expect(outcome('trader')).resolves.toEqual({
      to: '/login',
      search: { reason: 'unregistered' },
    });
  });

  it('does not hide a server failure behind a redirect', async () => {
    GQL.mockRejectedValue(new ApiError(500, 'Internal Server Error'));
    await expect(workspaceGuard('trader')({ context: { queryClient } })).rejects.toMatchObject({
      status: 500,
    });
  });

  it('treats an API that answers without a session (auth off) as signed in', async () => {
    GQL.mockResolvedValue({ viewer: ADMIN });
    await expect(outcome('trader')).resolves.toBeUndefined();
  });
});

describe('viewerGuard (the Guide: every role, no workspace)', () => {
  it('lets a trader and an admin in', async () => {
    GQL.mockResolvedValue({ viewer: TRADER });
    await expect(outcome('any')).resolves.toBeUndefined();
    queryClient.clear();
    GQL.mockResolvedValue({ viewer: ADMIN });
    await expect(outcome('any')).resolves.toBeUndefined();
  });

  it('sends no session to the login page', async () => {
    GQL.mockRejectedValue(new ApiError(401, 'Unauthorized'));
    await expect(outcome('any')).resolves.toEqual({ to: '/login', search: {} });
  });
});
