import { describe, expect, it } from 'vitest';

import { isRequestStatus, statusLabel, statusTone } from './labels';

describe('request status labels', () => {
  it('words each served status and tones it', () => {
    expect(statusLabel('WONT_DO')).toBe("Won't do");
    expect(statusTone('PROMOTED')).toBe('positive');
    expect(statusTone('UNMAPPED')).toBe('warning');
  });

  it('passes an unknown status through, neutral', () => {
    expect(statusLabel('NEW')).toBe('NEW');
    expect(statusTone('NEW')).toBe('neutral');
    expect(isRequestStatus('OPEN')).toBe(true);
    expect(isRequestStatus('open')).toBe(false);
  });
});
