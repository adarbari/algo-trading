import { describe, expect, it } from 'vitest';

import { exitRuleText } from './exit-rule';

const stop = {
  kind: 'HISTORY',
  fraction: 0.062,
  atr: null,
  multiple: null,
  winners: 80,
  beyond: 0.2,
  basis: 'ENTRY',
} as const;

const rule = {
  stop: null,
  edgeId: 'a',
  holdSessions: 5,
  winners: 0,
  inSampleOnly: false,
  takeProfit: null,
  takeProfitBasis: 'CREDIT',
  conditionFields: [] as string[],
  unknown: null,
} as const;
const noPrices = { stop: null, target: null, unknown: null } as const;

describe('exitRuleText', () => {
  it('names the served stop and hold and labels them backtested', () => {
    const text = exitRuleText({
      edgeId: 'a',
      stop,
      holdSessions: 5,
      winners: 80,
      inSampleOnly: false,
      unknown: null,
      takeProfit: null,
      takeProfitBasis: 'CREDIT',
      conditionFields: [],
    });
    expect(text).toBe(
      'Historical exit rule: stop 6.2% below the entry close; hold 5 sessions. Backtested (hypothetical).',
    );
  });

  it('gives an ATR stop as its multiple, never a product', () => {
    const text = exitRuleText({
      edgeId: 'a',
      stop: { ...stop, kind: 'FALLBACK', fraction: null, atr: 1.4, multiple: 2 },
      holdSessions: null,
      winners: 3,
      inSampleOnly: false,
      unknown: null,
      takeProfit: null,
      takeProfitBasis: 'CREDIT',
      conditionFields: [],
    });
    expect(text).toContain('stop 2.0 × ATR(14)');
    expect(text).not.toContain('hold');
  });

  it('is null when there is no stop and no hold to copy', () => {
    expect(
      exitRuleText({
        edgeId: 'a',
        stop: null,
        holdSessions: null,
        winners: 0,
        inSampleOnly: false,
        unknown: null,
        takeProfit: null,
        takeProfitBasis: 'CREDIT',
        conditionFields: [],
      }),
    ).toBeNull();
  });

  it('names a declared share stop and the target as a rise of the entry close, with the prices', () => {
    const text = exitRuleText(
      {
        ...rule,
        stop: { ...stop, kind: 'DECLARED', fraction: 0.05, winners: null, beyond: null },
        takeProfit: 0.1,
        takeProfitBasis: 'ENTRY',
      },
      { stop: 95, target: 110, unknown: null },
    );
    expect(text).toBe(
      'Historical exit rule: declared stop 5.0% below the entry close ($95.00); target 10.0% above the entry close ($110.00); hold 5 sessions. Backtested (hypothetical).',
    );
  });

  it("leaves an option setup's take profit (a share of the credit) out of the text", () => {
    const text = exitRuleText({ ...rule, takeProfit: 0.5, takeProfitBasis: 'CREDIT' }, noPrices);
    expect(text).not.toContain('target');
  });

  it("never calls an option setup's stop a fall below the entry close", () => {
    const credit = { ...stop, kind: 'DECLARED', fraction: 2, basis: 'CREDIT' } as const;
    expect(exitRuleText({ ...rule, stop: credit }, noPrices)).toContain(
      'declared stop 2.0 × the credit',
    );
    const collateral = { ...stop, fraction: 0.08, basis: 'COLLATERAL' } as const;
    const text = exitRuleText({ ...rule, stop: collateral }, noPrices);
    expect(text).toContain('stop 8.0% of the collateral');
    for (const t of [exitRuleText({ ...rule, stop: credit }, noPrices), text]) {
      expect(t).not.toContain('below the entry close');
    }
  });

  it('adds the served stop price to an ATR fallback stop', () => {
    const atr = { ...stop, kind: 'FALLBACK', fraction: null, atr: 1.5, multiple: 2 } as const;
    const text = exitRuleText({ ...rule, stop: atr }, { stop: 97, target: null, unknown: null });
    expect(text).toContain('stop 2.0 × ATR(14) ($97.00)');
  });
});
