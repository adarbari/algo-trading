import { describe, expect, it } from 'vitest';

import { draftState } from './state';

const base = { preset: null, dirty: false, nextVersion: 3, detail: { draft: null, latest: 2 } };

describe('draftState', () => {
  it('says unsaved changes first, then a saved draft, then the finalized version', () => {
    expect(draftState({ ...base, dirty: true }).label).toBe('DRAFT v3 · unsaved changes');
    expect(draftState({ ...base, detail: { draft: {}, latest: 2 } }).label).toBe('DRAFT v3');
    expect(draftState(base).label).toBe('v2 · finalized');
  });

  it('marks a preset until its first edit makes the copy', () => {
    const preset = { ...base, preset: { id: 'vrp' }, detail: { draft: null, latest: null } };
    expect(draftState(preset).label).toBe('Site preset');
    expect(draftState({ ...preset, dirty: true }).label).toBe('DRAFT v3 · unsaved changes');
  });
});
