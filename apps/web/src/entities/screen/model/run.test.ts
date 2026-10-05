import { describe, expect, it } from 'vitest';

import { isActive, runMessage, type ScreenRun } from './run';

const run = (state: string, error: string | null = null): ScreenRun => ({
  state,
  config_id: 'vrp_scanner',
  session: '2026-10-02',
  job_id: state === 'ready' ? null : 'job-1',
  run_id: null,
  error,
});

describe('isActive', () => {
  it('is true only while the job is queued or running', () => {
    expect(['queued', 'running'].map((s) => isActive(run(s)))).toEqual([true, true]);
    expect(['ready', 'complete', 'partial', 'failed'].map((s) => isActive(run(s)))).toEqual([
      false,
      false,
      false,
      false,
    ]);
    expect(isActive(undefined)).toBe(false);
  });
});

describe('runMessage', () => {
  it('says what happened in a few words', () => {
    expect(runMessage(undefined)).toBeNull();
    expect(runMessage(run('running'))).toBe('Running for 2026-10-02…');
    expect(runMessage(run('ready'))).toBe('Already up to date for 2026-10-02');
    expect(runMessage(run('complete'))).toBe('Updated for 2026-10-02');
    expect(runMessage(run('partial'))).toBe('Updated for 2026-10-02, with some data missing');
    expect(runMessage(run('failed', 'boom'))).toBe('The run failed: boom');
    expect(runMessage(run('failed'))).toBe('The run failed');
  });
});
