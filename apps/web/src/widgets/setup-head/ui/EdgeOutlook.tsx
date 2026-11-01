/**
 * What would change the verdict: the server's sentence (the first test not passed and what it
 * would take), the evidence collected against the evidence needed as meters (out-of-sample
 * trades toward Promising and Works, all trades toward Works; the caption is the projected date,
 * or why there is none), the verdict at the count on today's figures, when each count is expected
 * and the next trade to close, and the checks that say whether the result is real, one row each.
 * Every count, date, sentence and state is the server's; nothing is projected or judged here.
 */
import {
  EvidenceMeter,
  formatValue,
  IndicatorRow,
  Panel,
  Stack,
  Text,
  type EvidenceMilestone,
  type IndicatorStatus,
} from '@algotrade/ui';
import type { ReactNode } from 'react';

import { projectionLabel, verdictLabel, type EvidenceProgress } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

const CHECK_STATUS: Record<string, IndicatorStatus> = {
  pass: { tone: 'positive', label: 'Pass' },
  fail: { tone: 'negative', label: 'Fail' },
  not_measured: { tone: 'neutral', label: 'Not measured' },
  not_applicable: { tone: 'neutral', label: 'Does not apply' },
};

type Outlook = NonNullable<EvidenceProgress['outlook']>;

/** The projected date, or the state's words when there is none. */
function caption(outlook: Outlook | null): ReactNode {
  if (!outlook?.projectionState) return undefined;
  const state = projectionLabel(outlook.projectionState);
  return outlook.expectedBy
    ? `${state}: ${formatValue(outlook.expectedBy, { kind: 'date', style: 'short' }).text}`
    : state;
}

type Count = Outlook['projections'][number];

/** "40 out-of-sample ≈ Apr 2031", or the state's words when the count has no date. */
function countDate(count: Count): string {
  const what = `${String(count.needed)} ${count.oos ? 'out-of-sample' : 'trades'}`;
  if (count.expectedBy) {
    return `${what} ≈ ${formatValue(count.expectedBy, { kind: 'date', style: 'short' }).text}`;
  }
  return `${what}: ${projectionLabel(count.state)}`;
}

/** When each count still short is expected, then the next trade to close. */
function expectation(outlook: Outlook | null): string | undefined {
  if (!outlook) return undefined;
  const parts = outlook.projections.map(countDate);
  if (outlook.nextClose) {
    parts.push(
      `next closes ${formatValue(outlook.nextClose, { kind: 'date', style: 'short' }).text}`,
    );
  }
  return parts.length > 0 ? parts.join(' · ') : undefined;
}

export interface EdgeOutlookProps {
  evidence: EvidenceProgress;
}

export function EdgeOutlook({ evidence }: EdgeOutlookProps) {
  const outlook = evidence.outlook ?? null;
  const oosMilestones: EvidenceMilestone[] = [
    { at: evidence.needed, label: verdictLabel('promising') },
    ...(evidence.worksOosNeeded > evidence.needed
      ? [{ at: evidence.worksOosNeeded, label: verdictLabel('works') }]
      : []),
  ];
  const projected = caption(outlook);
  const dates = expectation(outlook);
  return (
    <Panel
      title="What would change the verdict"
      headingLevel={2}
      actions={
        <Stack direction="row" gap={1} align="center">
          {termHelp('verdict_outlook')}
          {termHelp('evidence_needed')}
        </Stack>
      }
    >
      <Stack gap={3}>
        {outlook && <Text>{outlook.sentence}</Text>}
        {outlook?.atTarget && <Text>{outlook.atTarget.sentence}</Text>}
        <Stack gap={3}>
          <EvidenceMeter
            label="Out-of-sample trades"
            value={evidence.oosTrades}
            max={Math.max(evidence.needed, evidence.worksOosNeeded)}
            milestones={oosMilestones}
            {...(outlook?.criterion === 'trades' && projected ? { caption: projected } : {})}
          />
          <EvidenceMeter
            label="All trades"
            value={evidence.wholeTrades}
            max={evidence.wholeNeeded}
            milestones={[{ at: evidence.wholeNeeded, label: verdictLabel('works') }]}
            {...(outlook?.criterion === 'works_trades' && projected ? { caption: projected } : {})}
          />
        </Stack>
        {dates && (
          <Text size="sm" tone="secondary">
            {dates}
          </Text>
        )}
        {evidence.checks.length > 0 && (
          <Stack as="ul" gap={0} aria-label="Checks that the result is real">
            {evidence.checks.map((check) => (
              <Stack as="li" key={check.id}>
                <IndicatorRow
                  status={CHECK_STATUS[check.status] ?? { tone: 'neutral', label: check.status }}
                  name={check.label}
                  description={`Needs ${check.threshold}`}
                  value={check.value}
                />
              </Stack>
            ))}
          </Stack>
        )}
      </Stack>
    </Panel>
  );
}
