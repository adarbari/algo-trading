import { describe, expect, it } from 'vitest';

import { previewPanelState } from './preview-state';

describe('previewPanelState', () => {
  it('is empty when idle, ready with data, error without data, else loading', () => {
    expect(previewPanelState({ data: undefined, error: null, idle: true })).toBe('empty');
    expect(previewPanelState({ data: {}, error: 'x', idle: false })).toBe('ready');
    expect(previewPanelState({ data: undefined, error: 'x', idle: false })).toBe('error');
    expect(previewPanelState({ data: undefined, error: null, idle: false })).toBe('loading');
  });
});
