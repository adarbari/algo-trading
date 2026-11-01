import { describe, expect, it } from 'vitest';

import { ADMIN, DEFAULT_WORKSPACE, section, TRADER, WORKSPACES } from './workspaces';

describe('workspaces', () => {
  it('opens on the trader workspace, ideas first', () => {
    expect(DEFAULT_WORKSPACE).toBe(TRADER);
    expect(TRADER.sections[0]?.path).toBe('/ideas');
  });

  it('shows Ideas, Setups, Test and Calendar on the bar', () => {
    expect(TRADER.sections.map((s) => s.label)).toEqual(['Ideas', 'Setups', 'Test', 'Calendar']);
  });

  it('keeps admin sections under /admin and every path unique', () => {
    expect(ADMIN.sections.every((s) => s.path.startsWith('/admin/'))).toBe(true);
    const paths = WORKSPACES.flatMap((w) => w.sections.map((s) => s.path));
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('finds a section by path and fails loudly for an unknown one', () => {
    expect(section(TRADER, '/edges').label).toBe('Setups');
    expect(() => section(TRADER, '/explore')).toThrow(/no section/);
  });
});
