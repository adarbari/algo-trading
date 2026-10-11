/**
 * The failure section of a call's detail: where it failed, the message, the prompt sent and, for
 * a rejected answer, the raw answer. Only a failed or rejected call has one.
 */
import { Heading, KeyValue, Stack, Text, TextBlock } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { STAGE_LABEL, TERM_OF_STAGE, type UsageCall } from '@/entities/llm-usage';
import { termHelp } from '@/features/guide-help';

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

export function FailureDetail({ call }: { call: UsageCall }) {
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
