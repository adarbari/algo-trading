import { describe, expect, it } from 'vitest';

import { EDGES_FIXTURE } from './fixtures';
import {
  inView,
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
    ]);
    expect(verdictTone('works')).toBe('positive');
    expect(verdictTone('not_working')).toBe('negative');
    expect(verdictTone('something else')).toBe('neutral');
    expect(verdictLabel('something else')).toBe('something else');
  });
});

describe("the user's state about an edge", () => {
  const [momentum, , mine, , rejected] = [
    ...EDGES_FIXTURE.edges.slice(0, 1),
    undefined,
    ...EDGES_FIXTURE.edges.slice(1, 2),
    undefined,
    ...EDGES_FIXTURE.edges.slice(-1),
  ];

  it('words the states and the permanent warnings', () => {
    expect(stateLabel('following')).toBe('Following');
    expect(stateTone('following')).toBe('positive');
    expect(stateTone('rejected')).toBe('negative');
    expect(labelText('followed_against_verdict')).toBe('Followed against the verdict');
    expect(labelText('new_label')).toBe('new_label');
  });

  it('files an edge under a view, and shows the site status until the user has a state', () => {
    expect(momentum && inView(momentum, 'mine')).toBe(false);
    expect(mine && inView(mine, 'mine')).toBe(true);
    expect(rejected && inView(rejected, 'rejected')).toBe(true); // the site rejected it
    expect(momentum && inView({ ...momentum, state: 'following' }, 'following')).toBe(true);
    expect(momentum && inView(momentum, 'all')).toBe(true);
    expect(momentum && stateOrStatus(momentum)).toBe('Candidate');
    expect(momentum && stateOrStatus({ ...momentum, state: 'retired' })).toBe('Retired');
  });
});
