import { beforeEach, describe, expect, it } from 'vitest';

import { lastWorkspace, rememberWorkspace } from './last-workspace';
import { ADMIN, TRADER } from './workspaces';

beforeEach(() => {
  sessionStorage.clear();
});

describe('lastWorkspace', () => {
  it('is the workspace last remembered (the Guide keeps the one the user came from)', () => {
    rememberWorkspace(ADMIN);
    expect(lastWorkspace()).toBe(ADMIN);
    rememberWorkspace(TRADER);
    expect(lastWorkspace()).toBe(TRADER);
  });
});
