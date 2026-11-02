import { describe, expect, it } from 'vitest';

import { EDGES_FIXTURE } from './fixtures';
import {
  labelText,
  stateLabel,
  stateOrStatus,
  stateTone,
  statusLabel,
  statusTone,
  verdictLabel,
  verdictTone,
  VERDICT_ORDER,
} from './edges';

describe('status words', () => {
  it('capitalises the status and gives each a tone', () => {
    expect(statusLabel('candidate')).toBe('Candidate');
    expect(statusLabel('researching')).toBe('Researching');
    expect(statusTone('researching')).toBe('neutral');
    expect(statusLabel('unheard')).toBe('unheard');
    expect(statusTone('evidenced')).toBe('positive');
    expect(statusTone('rejected')).toBe('negative');
    expect(statusTone('anything else')).toBe('neutral');
  });
});

describe('verdict words', () => {
  it('words and tones every served verdict, best first', () => {
    expect(VERDICT_ORDER.map(verdictLabel)).toEqual([
      'Works',
      'Promising',
      'Not working',
      'Not enough data',
      'Waiting on data',
      'Diagnostic only',
    ]);
    expect(verdictTone('works')).toBe('positive');
    expect(verdictTone('promising')).toBe('accent');
    expect(verdictTone('not_working')).toBe('neutral');
    expect(verdictTone('something else')).toBe('neutral');
    expect(verdictLabel('something else')).toBe('something else');
  });
});

describe("the user's state about an edge", () => {
  const momentum = EDGES_FIXTURE.edges[0];

  it('words the states and the permanent warnings', () => {
    expect(stateLabel('following')).toBe('Following');
    expect(stateTone('following')).toBe('positive');
    expect(stateTone('rejected')).toBe('negative');
    expect(labelText('followed_against_verdict')).toBe('Followed against the verdict');
    expect(labelText('new_label')).toBe('new_label');
  });

  it('shows the site status until the user has a state', () => {
    expect(momentum && stateOrStatus(momentum)).toBe('Candidate');
    expect(momentum && stateOrStatus({ ...momentum, state: 'retired' })).toBe('Retired');
  });
});
