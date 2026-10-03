import { describe, expect, it } from 'vitest';

import { formatDuration } from './duration';

describe('formatDuration', () => {
  it('reads seconds, minutes and hours', () => {
    expect(formatDuration(0.265)).toBe('0.3s');
    expect(formatDuration(12.4)).toBe('12s');
    expect(formatDuration(1559.668)).toBe('26m 0s');
    expect(formatDuration(4860)).toBe('1h 21m');
  });

  it('shows a missing duration as a dash', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(undefined)).toBe('—');
  });
});
