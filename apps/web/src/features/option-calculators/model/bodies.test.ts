import { describe, expect, it } from 'vitest';

import { callsBody, rollBody } from './bodies';

const NONE = { includeDebits: false, sameDelta: false };

describe('rollBody', () => {
  it('needs a strike and an expiry', () => {
    expect(rollBody('ORBT', { strike: null, expiry: '2026-10-30', soldAt: null }, NONE)).toBeNull();
    expect(rollBody('ORBT', { strike: 80, expiry: '', soldAt: null }, NONE)).toBeNull();
    expect(rollBody('ORBT', { strike: 0, expiry: '2026-10-30', soldAt: null }, NONE)).toBeNull();
  });

  it('passes what was typed, as a put, with the choices', () => {
    expect(
      rollBody(
        'ORBT',
        { strike: 80, expiry: '2026-10-30', soldAt: 1.4 },
        { includeDebits: true, sameDelta: false },
      ),
    ).toEqual({
      key: 'ORBT',
      right: 'put',
      strike: 80,
      expiry: '2026-10-30',
      sold_at: 1.4,
      include_debits: true,
      same_delta: false,
    });
  });

  it('leaves the sold-at price empty when none was typed', () => {
    expect(
      rollBody('ORBT', { strike: 80, expiry: '2026-10-30', soldAt: null }, NONE)?.sold_at,
    ).toBe(null);
  });
});

describe('callsBody', () => {
  it('needs whole shares and a price', () => {
    expect(callsBody('ORBT', { shares: null, price: 80 })).toBeNull();
    expect(callsBody('ORBT', { shares: 150.5, price: 80 })).toBeNull();
    expect(callsBody('ORBT', { shares: 0, price: 80 })).toBeNull();
    expect(callsBody('ORBT', { shares: 100, price: null })).toBeNull();
    expect(callsBody('ORBT', { shares: 100, price: 0 })).toBeNull();
    expect(callsBody('ORBT', { shares: 10_000_001, price: 80 })).toBeNull();
  });

  it('passes the shares and the price as typed', () => {
    expect(callsBody('ORBT', { shares: 300, price: 78.5 })).toEqual({
      key: 'ORBT',
      shares: 300,
      price: 78.5,
    });
  });
});
