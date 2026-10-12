import { describe, expect, it } from 'vitest';

import { feasibilityLabel, statusLabel } from './labels';

describe('feasibilityLabel', () => {
  it('names each feasibility with its own Guide term', () => {
    expect(feasibilityLabel('ROLLUP_FROM_STORED')).toMatchObject({
      label: 'Buildable from stored data',
      help: { id: 'describe_feasibility_rollup' },
    });
    expect(feasibilityLabel('NEEDS_SOURCE').help.id).toBe('describe_feasibility_source');
    expect(feasibilityLabel('UNCLEAR').help.id).toBe('describe_feasibility_unclear');
  });

  it('reads a value it does not know as unclear', () => {
    expect(feasibilityLabel('SOMETHING_NEW').label).toBe('Unclear');
  });
});

describe('statusLabel', () => {
  it('names each request status with its own Guide term, and none for an unknown one', () => {
    expect(statusLabel('OPEN')?.help.id).toBe('describe_status_open');
    expect(statusLabel('PROMOTED')?.help.id).toBe('describe_status_promoted');
    expect(statusLabel('WONT_DO')).toMatchObject({ label: "Won't do" });
    expect(statusLabel('ARCHIVED')).toBeNull();
  });
});
