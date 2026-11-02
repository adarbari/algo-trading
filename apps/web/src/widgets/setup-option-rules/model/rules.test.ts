import { describe, expect, it } from 'vitest';

import { OPTION_SETUP_FIXTURE } from '@/entities/edge';

import { exitText, ruleRows } from './rules';

const rules = OPTION_SETUP_FIXTURE.rules;
if (rules == null) throw new Error('the fixture declares rules');

const value = (id: string) => ruleRows(rules).find((r) => r.id === id)?.value;

describe('an option setup rules rows', () => {
  it('words each declared part from the structured values', () => {
    expect(value('decides')).toBe('Every session');
    expect(value('enters')).toBe('1 session after the decision');
    expect(value('leg-0')).toBe('1 put, 0.30 delta, 30 days');
    expect(ruleRows(rules).find((r) => r.id === 'leg-0')?.label).toBe('Sell');
    expect(value('expiry')).toBe('about 30 days out, monthly cycle');
    expect(value('exit')).toBe(
      'take 50% of the credit; stop at 2 times the credit; close at 21 days to expiry; when iv_rank says so',
    );
    expect(value('collateral')).toContain('Cash secured');
    expect(value('reports')).toContain('Skips');
    expect(value('case')).toBe('strike');
  });

  it('leaves out an exit, a report rule and per-pick settings the document does not declare', () => {
    const bare = {
      ...rules,
      takeProfit: null,
      stopLoss: null,
      exitDte: null,
      exitConditionFields: [],
      skipReportInLife: false,
      caseValued: [],
    };
    expect(exitText(bare)).toBeNull();
    const ids = ruleRows(bare).map((r) => r.id);
    expect(ids).not.toContain('exit');
    expect(ids).not.toContain('reports');
    expect(ids).not.toContain('case');
  });

  it('words a bought leg, an out-of-the-money strike and an own tenor', () => {
    const [leg] = rules.legs;
    if (leg == null) throw new Error('a leg');
    const bought = {
      ...rules,
      legs: [{ ...leg, qty: 2, right: 'C', strike: 'otm_pct', otmPct: 0.05, tenorDays: 45 }],
    };
    const row = ruleRows(bought).find((r) => r.id === 'leg-0');
    expect(row).toMatchObject({ label: 'Buy', value: '2 calls, 5% out of the money, 45 days' });
  });
});
