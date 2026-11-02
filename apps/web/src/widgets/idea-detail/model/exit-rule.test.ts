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
});
