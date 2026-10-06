import { describe, expect, it } from 'vitest';

import { ADMIN, DEFAULT_WORKSPACE, section, TRADER, WORKSPACES } from './workspaces';

describe('workspaces', () => {
  it('opens on the trader workspace, ideas first', () => {
    expect(DEFAULT_WORKSPACE).toBe(TRADER);
    expect(TRADER.sections[0]?.path).toBe('/ideas');
  });

  it('keeps admin sections under /admin and every path unique', () => {
    expect(ADMIN.sections.every((s) => s.path.startsWith('/admin/'))).toBe(true);
    const paths = WORKSPACES.flatMap((w) => w.sections.map((s) => s.path));
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('finds a section by path and fails loudly for an unknown one', () => {
    expect(section(TRADER, '/explore').label).toBe('Explore');
    expect(() => section(ADMIN, '/explore')).toThrow(/no section/);
  });
});
