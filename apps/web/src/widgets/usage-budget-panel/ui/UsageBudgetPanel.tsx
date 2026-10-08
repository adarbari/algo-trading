/**
 * Spend against the budget: one tile per window (today, 7 days, 30 days, month to date) with
 * what counts against the budget, the notional seat cost beside it (never added into it) and the
 * tokens, and a meter of the share of the cap used for the two windows that have one (a day, a
 * month). No cap set reads as "no cap", not as zero used. Every number is the server's.
 */
import {
  Banner,
  formatValue,
  Grid,
  KeyValue,
  ScoreMeter,
  Stack,
  StatStrip,
  Text,
  type StatItem,
} from '@algotrade/ui';

import { unknownText } from '@/entities/availability';
import {
  PERCENT,
  TOKENS,
  UsagePanel,
  USD,
  WINDOW_LABEL,
  type LlmUsage,
  type UsageWindow,
} from '@/entities/llm-usage';
import { GuideHelp } from '@/features/guide-help';

const THRESHOLDS = [
  { at: 75, label: 'near the cap', tone: 'warning' },
  { at: 100, label: 'at the cap', tone: 'negative' },
] as const;

const usd = (value: number) => formatValue(value, USD).text;
const count = (value: number) => formatValue(value, TOKENS).text;

function tile(w: UsageWindow): StatItem {
  const t = w.tally;
  const capped = w.cap?.usedShare != null && w.cap.usedShare >= 1;
  const tokens = t.unknown
    ? `tokens: ${unknownText(t.unknown)}`
    : `${count(t.inputTokens)} in · ${count(t.outputTokens)} out`;
  return {
    id: w.key,
    label: WINDOW_LABEL[w.key] ?? w.key,
    value: usd(t.spentUsd),
    tone: capped ? 'negative' : 'default',
    sub: (
      <Stack gap={0}>
        <Text size="sm" tone="muted">{`${count(t.calls)} calls · ${tokens}`}</Text>
        {t.reportedUsd > 0 && (
          <Text size="sm" tone="muted">{`of which ${usd(t.reportedUsd)} notional (reported)`}</Text>
        )}
        {t.callsWithoutTokens > 0 && !t.unknown && (
          <Text
            size="sm"
            tone="muted"
          >{`${count(t.callsWithoutTokens)} calls reported no tokens`}</Text>
        )}
      </Stack>
    ),
  };
}

function Meter({ w, usage }: { w: UsageWindow; usage: LlmUsage }) {
  const cap = w.cap;
  if (!cap) return null;
  const name = `${WINDOW_LABEL[w.key] ?? w.key} against the ${cap.kind} cap`;
  return (
    <ScoreMeter
      label={name}
      value={cap.usedShare == null ? null : cap.usedShare * 100}
      unit="%"
      max={120}
      thresholds={THRESHOLDS}
      baseLabel="within the cap"
      size="md"
      unknownReason={usage.budget.error ? 'The budget could not be read' : `No ${cap.kind} cap set`}
      caption={
        cap.limitUsd == null
          ? undefined
          : `${usd(w.tally.spentUsd)} of ${usd(cap.limitUsd)} (${formatValue(cap.usedShare, PERCENT).text})`
      }
    />
  );
}

function Budget({ usage }: { usage: LlmUsage }) {
  const b = usage.budget;
  const caps = usage.windows.filter((w) => w.cap);
  return (
    <Stack gap={4}>
      {b.error && (
        <Banner tone="warning" title="The budget could not be read">
          {b.error}
        </Banner>
      )}
      <StatStrip label="Spend by window" items={usage.windows.map(tile)} />
      <Grid columns={2} gap={4} collapse="md">
        {caps.map((w) => (
          <Meter key={w.key} w={w} usage={usage} />
        ))}
      </Grid>
      <KeyValue
        label="Budget settings"
        layout="columns"
        items={[
          { id: 'daily', label: 'Daily cap', value: b.dailyUsd == null ? 'none' : usd(b.dailyUsd) },
          {
            id: 'monthly',
            label: 'Monthly cap',
            value: b.monthlyUsd == null ? 'none' : usd(b.monthlyUsd),
          },
          { id: 'over', label: 'When a cap is reached', value: b.over ?? 'unknown' },
          {
            id: 'bound',
            label: 'Reserved per Claude Code call',
            value: b.reportedCallUsd == null ? 'unknown' : usd(b.reportedCallUsd),
          },
        ]}
      />
    </Stack>
  );
}

export function UsageBudgetPanel() {
  return (
    <UsagePanel
      title="Spend against the budget"
      description="what counts against the cap: priced, reported and bound costs; free calls add nothing"
      actions={
        <Stack direction="row" gap={1}>
          <GuideHelp entry={{ kind: 'term', id: 'llm_cost_basis' }} />
          <GuideHelp entry={{ kind: 'term', id: 'llm_budget' }} />
        </Stack>
      }
      needsCalls={false}
    >
      {(usage) => <Budget usage={usage} />}
    </UsagePanel>
  );
}
