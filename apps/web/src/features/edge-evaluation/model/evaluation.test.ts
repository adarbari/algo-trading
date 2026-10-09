import { describe, expect, it } from 'vitest';

import { evaluationMessage, isActive, type EvaluationRun } from './evaluation';

const run = (state: string, extra: Partial<EvaluationRun> = {}): EvaluationRun => ({
  state,
  exploratory: null,
  error: null,
  ...extra,
});

describe('evaluation run', () => {
  it('polls only while queued or running', () => {
    expect(isActive(run('queued'))).toBe(true);
    expect(isActive(run('running'))).toBe(true);
    expect(isActive(run('complete'))).toBe(false);
    expect(isActive(undefined)).toBe(false);
  });

  it('says what happened in a few words', () => {
    expect(evaluationMessage(undefined)).toBeNull();
    expect(evaluationMessage(run('running'))).toBe('Evaluating…');
    expect(evaluationMessage(run('complete', { exploratory: true }))).toBe('Done (exploratory)');
    expect(evaluationMessage(run('complete', { exploratory: false }))).toBe('Done');
    expect(evaluationMessage(run('partial'))).toBe('Done, with some data missing');
    expect(evaluationMessage(run('failed', { error: 'boom' }))).toBe('The evaluation failed: boom');
    expect(evaluationMessage(run('failed'))).toBe('The evaluation failed');
  });
});
