import { describe, expect, it } from 'vitest';

import { DISTANT, LinkModel, roundTripDepth } from './model';

describe('LinkModel', () => {
  it('charges the connection two round trips and the request one', () => {
    const model = new LinkModel(DISTANT);
    expect(model.delay(0, 0)).toBe(3 * DISTANT.rttMs);
    expect(model.delay(1000, 0)).toBe(DISTANT.rttMs); // the connection is open
  });

  it('adds slow-start rounds to a large response, none to one within the first window', () => {
    const small = new LinkModel(DISTANT).delay(0, 10_000);
    const large = new LinkModel(DISTANT).delay(0, 400_000);
    expect(small).toBeLessThan(3 * DISTANT.rttMs + 10);
    expect(large).toBeGreaterThan(5 * DISTANT.rttMs);
  });

  it('queues responses on the one downlink', () => {
    const model = new LinkModel({ rttMs: 100, downMbit: 8 }); // 1000 bytes per ms
    model.delay(0, 0);
    const first = model.delay(1000, 14_000);
    const second = model.delay(1000, 14_000);
    expect(second).toBeGreaterThanOrEqual(first + 14);
  });
});

describe('roundTripDepth', () => {
  it('is 1 for requests that all start before anything finishes', () => {
    expect(
      roundTripDepth([
        { start: 0, end: 300 },
        { start: 5, end: 400 },
      ]),
    ).toBe(1);
  });

  it('counts a chain: a request that starts after another finished is one deeper', () => {
    expect(
      roundTripDepth([
        { start: 0, end: 300 },
        { start: 300, end: 600 },
        { start: 310, end: 900 },
        { start: 900, end: 1200 },
      ]),
    ).toBe(3);
  });
});
