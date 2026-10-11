/**
 * One stored call in full: when, provider, model, use case, user, tokens, latency, cost and how
 * it was worked out, the outcome and the provider it fell back from, the run that wrote it. A
 * value the log holds as null reads "unknown" with the reason beside it, never as zero. A failed
 * or rejected call also shows where it failed, the message, the prompt sent and the raw answer.
 */
import { EmptyState, Heading, KeyValue, Stack, Text, TextBlock } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { UnknownNote } from '@/entities/availability';
import {
  BasisBadge,
  findCall,
  OutcomeBadge,
  stamp,
  STAGE_LABEL,
  TERM_OF_STAGE,
  TOKENS,
  UsagePanel,
  USD,
  type UsageCall,
} from '@/entities/llm-usage';
import { termHelp } from '@/features/guide-help';

export interface UsageCallDetailProps {
  /** The chosen call (its `callId`), if any. */
  selected: string | null;
}

const UNKNOWN_FIELD: Record<string, string> = {
  input_tokens: 'Input tokens',
  output_tokens: 'Output tokens',
  cost_usd: 'Cost',
};

function Captioned({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <Stack gap={1}>
      <Text size="sm" tone="muted">
        {caption}
      </Text>
      {children}
    </Stack>
  );
}

function Failure({ call }: { call: UsageCall }) {
  const prompt =
    call.promptChars === null
      ? 'unknown'
      : `${call.promptChars.toLocaleString('en-US')} characters`;
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={3}>Failure</Heading>
        {termHelp(TERM_OF_STAGE)}
      </Stack>
      <KeyValue
        label="Failure"
        layout="columns"
        items={[
          {
            id: 'stage',
            label: 'Where',
            value: call.stage ? (STAGE_LABEL[call.stage] ?? call.stage) : 'unknown',
          },
          { id: 'prompt', label: 'Prompt length', value: prompt },
        ]}
      />
      <Captioned caption="Error message">
        <TextBlock label="Error message" text={call.error} size="sm" empty="No message kept" />
      </Captioned>
      <Captioned caption="Prompt sent (what the trader typed)">
        <TextBlock
          label="Prompt sent (what the trader typed)"
          text={call.sentence}
          size="sm"
          empty="No prompt kept"
        />
      </Captioned>
      {call.stage === 'answer' && (
        <Captioned caption="Raw model answer">
          <TextBlock label="Raw model answer" text={call.answer} empty="No answer kept" />
        </Captioned>
      )}
    </Stack>
  );
}

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
      {(call.stage || call.error) && <Failure call={call} />}
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
