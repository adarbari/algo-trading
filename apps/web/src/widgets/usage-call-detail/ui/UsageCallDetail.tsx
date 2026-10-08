/**
 * One stored call in full: when, provider, model, use case, user, tokens, latency, cost and how
 * it was worked out, the outcome and the provider it fell back from, the run that wrote it. A
 * value the log holds as null reads "unknown" with the reason beside it, never as zero.
 */
import { EmptyState, KeyValue, Stack, Text } from '@algotrade/ui';

import { UnknownNote } from '@/entities/availability';
import {
  BasisBadge,
  findCall,
  OutcomeBadge,
  stamp,
  TOKENS,
  UsagePanel,
  USD,
  type UsageCall,
} from '@/entities/llm-usage';

export interface UsageCallDetailProps {
  /** The chosen call (its `callId`), if any. */
  selected: string | null;
}

const UNKNOWN_FIELD: Record<string, string> = {
  input_tokens: 'Input tokens',
  output_tokens: 'Output tokens',
  cost_usd: 'Cost',
};

function Detail({ call }: { call: UsageCall }) {
  return (
    <Stack gap={3}>
      <KeyValue
        label="Call"
        layout="columns"
        items={[
          { id: 'ts', label: 'When', value: stamp(call.ts), mono: true },
          { id: 'provider', label: 'Provider', value: call.provider },
          { id: 'model', label: 'Model', value: call.model, mono: true },
          { id: 'useCase', label: 'Use case', value: call.useCase },
          { id: 'user', label: 'User', value: call.user ?? 'unknown' },
          { id: 'in', label: 'Input tokens', value: call.inputTokens, format: TOKENS },
          { id: 'out', label: 'Output tokens', value: call.outputTokens, format: TOKENS },
          {
            id: 'latency',
            label: 'Latency (s)',
            value: call.latencyS,
            format: { kind: 'number', digits: 2 },
          },
          { id: 'cost', label: 'Cost', value: call.costUsd, format: USD },
          { id: 'basis', label: 'Cost basis', value: <BasisBadge basis={call.costBasis} /> },
          { id: 'outcome', label: 'Outcome', value: <OutcomeBadge outcome={call.outcome} /> },
          { id: 'from', label: 'Fell back from', value: call.fellBackFrom ?? 'nothing' },
          { id: 'run', label: 'Written by run', value: call.runId, mono: true },
        ]}
      />
      {call.unknown && (
        <Stack gap={1}>
          <Text size="sm" tone="muted">
            {`Not known: ${call.unknownFields.map((f) => UNKNOWN_FIELD[f] ?? f).join(', ')}`}
          </Text>
          <UnknownNote unknown={call.unknown} />
        </Stack>
      )}
    </Stack>
  );
}

export function UsageCallDetail({ selected }: UsageCallDetailProps) {
  return (
    <UsagePanel title="Call detail" rows={4}>
      {(usage) => {
        const call = findCall(usage, selected);
        return call ? (
          <Detail call={call} />
        ) : (
          <EmptyState
            compact
            title={selected ? 'That call is no longer in the latest list' : 'No call selected'}
            description="Select a row of the recent calls."
          />
        );
      }}
    </UsagePanel>
  );
}
