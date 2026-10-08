/**
 * How the last 30 days of attempts ended: answered, answered by a later provider (fallback),
 * failed, skipped for the budget; with the fallback and failure rates. A failure rate is the
 * signal that calls are lost and a paid attempt that failed may still have been billed.
 */
import { formatValue, StatStrip, type StatItem } from '@algotrade/ui';

import { PERCENT, TOKENS, UsagePanel, type UsageReliability } from '@/entities/llm-usage';
import { GuideHelp } from '@/features/guide-help';

const count = (n: number) => formatValue(n, TOKENS).text;

function items(r: UsageReliability): StatItem[] {
  return [
    { id: 'attempts', label: 'Attempts', value: count(r.attempts) },
    { id: 'ok', label: 'Answered first time', value: count(r.ok), tone: 'positive' },
    {
      id: 'fell',
      label: 'Fell back',
      value: count(r.fellBack),
      sub: `rate ${formatValue(r.fallbackRate, PERCENT).text}`,
      tone: r.fellBack > 0 ? 'warning' : 'default',
    },
    {
      id: 'failed',
      label: 'Failed',
      value: count(r.failed),
      sub: `rate ${formatValue(r.failureRate, PERCENT).text}`,
      tone: r.failed > 0 ? 'negative' : 'default',
    },
    { id: 'skipped', label: 'Skipped for budget', value: count(r.skippedBudget) },
  ];
}

export function UsageReliabilityPanel() {
  return (
    <UsagePanel
      title="Fallbacks and failures"
      description="last 30 days"
      actions={<GuideHelp entry={{ kind: 'term', id: 'llm_fallback' }} />}
      rows={2}
    >
      {(usage) => <StatStrip label="How attempts ended" items={items(usage.reliability)} />}
    </UsagePanel>
  );
}
