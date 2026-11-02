/**
 * The rows of an option setup's rules (ADR 0088): the served structured values said in words, one
 * row each with the Guide term its help button opens. It words what the document declares and
 * computes nothing: a share of the credit is shown as a percent, a count as a count.
 */
import { formatValue } from '@algotrade/ui';

import type { OptionLeg, OptionRules } from '@/entities/edge';

export interface RuleRow {
  id: string;
  label: string;
  value: string;
  /** The Guide term the row's help button opens. */
  help: string;
}

const SCHEDULES: Record<string, string> = {
  every_session: 'Every session',
  month_end: 'Each month end',
};
const COLLATERALS: Record<string, string> = {
  cash_secured: 'Cash secured: the cash to buy the shares if assigned',
  max_loss: 'The most the position can lose',
  regt: 'Reg T margin',
};
const CYCLES: Record<string, string> = { monthly: 'monthly', weekly: 'weekly', any: 'any' };
const RIGHTS: Record<string, string> = { P: 'put', C: 'call' };

const percent = (fraction: number, digits = 0): string =>
  formatValue(fraction, { kind: 'percent', digits }).text;
const plural = (n: number, word: string): string => `${String(n)} ${word}${n === 1 ? '' : 's'}`;
const words = (code: string): string => code.replaceAll('_', ' ');

/** The strike rule of a leg: its delta, "at the money" or a percent out of the money. */
function strikeText(leg: OptionLeg): string {
  if (leg.strike === 'delta' && leg.delta != null) return `${leg.delta.toFixed(2)} delta`;
  if (leg.strike === 'otm_pct' && leg.otmPct != null)
    return `${percent(leg.otmPct)} out of the money`;
  if (leg.strike === 'atm') return 'at the money';
  return leg.strike == null ? 'by its own rule' : words(leg.strike);
}

/** One leg as a row: "Sell" with "1 put, 0.30 delta, 30 days", the quantity's sign the side. */
export function legRow(leg: OptionLeg, index: number, tenorDays: number | null): RuleRow {
  const side = leg.qty < 0 ? 'Sell' : 'Buy';
  const qty = Math.abs(leg.qty);
  if (leg.kind === 'shares') {
    return {
      id: `leg-${String(index)}`,
      label: side,
      value: plural(qty, 'share'),
      help: 'option_rule_leg',
    };
  }
  const right = RIGHTS[leg.right ?? ''] ?? 'option';
  const tenor = leg.tenorDays ?? tenorDays;
  const parts = [plural(qty, right), strikeText(leg)];
  if (tenor != null) parts.push(plural(tenor, 'day'));
  return {
    id: `leg-${String(index)}`,
    label: side,
    value: parts.join(', '),
    help: 'option_rule_leg',
  };
}

/** The declared exits in one sentence-less list: each exit the document declares, in its own terms. */
export function exitText(rules: OptionRules): string | null {
  const exits: string[] = [];
  if (rules.takeProfit != null) exits.push(`take ${percent(rules.takeProfit)} of the credit`);
  if (rules.stopLoss != null) exits.push(`stop at ${String(rules.stopLoss)} times the credit`);
  if (rules.exitDte != null) exits.push(`close at ${plural(rules.exitDte, 'day')} to expiry`);
  if (rules.exitConditionFields.length > 0) {
    exits.push(`when ${rules.exitConditionFields.join(', ')} says so`);
  }
  return exits.length === 0 ? null : exits.join('; ');
}

/** Every row of the option rules, in the order a trader reads a plan: when, what, how it ends. */
export function ruleRows(rules: OptionRules): RuleRow[] {
  const rows: RuleRow[] = [
    {
      id: 'decides',
      label: 'Decides',
      value: SCHEDULES[rules.schedule] ?? words(rules.schedule),
      help: 'option_rule_decides',
    },
    {
      id: 'enters',
      label: 'Enters',
      value:
        rules.startOffsetSessions === 0
          ? 'At the decision session'
          : `${plural(rules.startOffsetSessions, 'session')} after the decision`,
      help: 'option_rule_enters',
    },
    ...rules.legs.map((leg, i) => legRow(leg, i, rules.tenorDays)),
    {
      id: 'expiry',
      label: 'Expiry',
      value: [
        rules.tenorDays == null ? null : `about ${plural(rules.tenorDays, 'day')} out`,
        `${CYCLES[rules.expiryCycle] ?? rules.expiryCycle} cycle`,
      ]
        .filter((part) => part != null)
        .join(', '),
      help: 'option_rule_expiry',
    },
  ];
  const exits = exitText(rules);
  if (exits !== null) {
    rows.push({ id: 'exit', label: 'Exit', value: exits, help: 'option_rule_exit' });
  }
  rows.push({
    id: 'collateral',
    label: 'Cash set aside',
    value: COLLATERALS[rules.collateral] ?? words(rules.collateral),
    help: 'idea_cash_set_aside',
  });
  if (rules.skipReportInLife) {
    rows.push({
      id: 'reports',
      label: 'Reports',
      value: 'Skips a name that reports before expiry',
      help: 'option_rule_reports',
    });
  }
  if (rules.caseValued.length > 0) {
    rows.push({
      id: 'case',
      label: 'Chosen per pick',
      value: rules.caseValued.map(words).join(', '),
      help: 'option_rule_case_valued',
    });
  }
  return rows;
}
