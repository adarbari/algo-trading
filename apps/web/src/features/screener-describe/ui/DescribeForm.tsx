/**
 * "Describe it": a sentence ("optionable stocks over $5 with IV rank above 50%") sent for a
 * draft; the answer is handed to the Builder as unsaved rows, and what the model dropped (a field
 * the catalogue does not have, a value the validator refused) or could not map is shown so the
 * trader knows what to add by hand. Each field named (left out or kept) carries the widget's
 * help button (`renderFieldHelp`: the Guide's drawer; features never import each other). The
 * API's refusal (drafting off, the model down) is the field's error.
 */
import { Banner, Button, Field, Input, Mono, Stack, Text } from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import type { ScreenDocument } from '@/entities/screen';
import { errorDetail } from '@/shared/api';

import { useDraftFromText, type ScreenDraft } from '../api/hooks';

export interface DescribeFormProps {
  screenerId: string;
  /** The Builder's working document: its criteria are kept unless the sentence changes them. */
  document: ScreenDocument;
  /** The draft the model proposed: load it into the Builder as an unsaved edit. */
  onDraft: (document: Readonly<Record<string, unknown>>) => void;
  /** The help for a field the draft names (null for a field the Guide does not know). */
  renderFieldHelp?: (field: string) => ReactNode;
}

const HINT =
  'Plain English, e.g. "optionable stocks over $5 with IV rank above 50% and $50M traded a day". The rows are a draft you review.';

/** The criteria of a draft with the field each reads. */
function keptFields(document: Readonly<Record<string, unknown>>): { id: string; field: string }[] {
  const criteria = document['criteria'];
  if (typeof criteria !== 'object' || criteria === null) return [];
  return Object.entries(criteria).flatMap(([id, criterion]) => {
    const field: unknown =
      typeof criterion === 'object' && criterion !== null && 'field' in criterion
        ? criterion.field
        : null;
    return typeof field === 'string' ? [{ id, field }] : [];
  });
}

export function DescribeForm({
  screenerId,
  document,
  onDraft,
  renderFieldHelp,
}: DescribeFormProps) {
  const [text, setText] = useState('');
  const [result, setResult] = useState<ScreenDraft | null>(null);
  const draft = useDraftFromText(screenerId);
  const canSubmit = text.trim() !== '' && !draft.isPending;
  const submit = () => {
    if (!canSubmit) return;
    draft.mutate(
      { text: text.trim(), document },
      {
        onSuccess: (answer) => {
          setResult(answer);
          onDraft(answer.document);
        },
      },
    );
  };
  const error = draft.isError ? errorDetail(draft.error) : undefined;
  const keptCriteria = result ? keptFields(result.document) : [];
  const kept = keptCriteria.length;
  return (
    <Stack gap={3}>
      <Field label="Describe the screen" hint={HINT} error={error}>
        <Input
          value={text}
          onValueChange={setText}
          onKeyDown={(event) => {
            if (event.key === 'Enter') submit();
          }}
          placeholder="Which instruments, which thresholds, how to rank"
          autoComplete="off"
          end={
            <Button
              variant="primary"
              size="sm"
              onClick={submit}
              disabled={!canSubmit}
              loading={draft.isPending}
            >
              Draft it
            </Button>
          }
        />
      </Field>
      {result && (
        <Banner
          tone={result.dropped.length > 0 ? 'warning' : 'info'}
          title={`Drafted ${String(kept)} ${kept === 1 ? 'criterion' : 'criteria'}; review and save`}
          onDismiss={() => {
            setResult(null);
          }}
        >
          <Stack gap={1}>
            {result.dropped.map((d) => (
              <Stack key={d.id} direction="row" gap={1} align="center" wrap>
                <Text size="sm">{`Left out ${d.id} (`}</Text>
                <Mono size="sm">{d.field}</Mono>
                {renderFieldHelp?.(d.field)}
                <Text size="sm">{`): ${d.reason}`}</Text>
              </Stack>
            ))}
            {keptCriteria.map(({ id, field }) => (
              <Stack key={id} direction="row" gap={1} align="center" wrap>
                <Text size="sm" tone="muted">{`Kept ${id}:`}</Text>
                <Mono size="sm">{field}</Mono>
                {renderFieldHelp?.(field)}
              </Stack>
            ))}
            {result.notes.map((note) => (
              <Text key={note} size="sm" tone="muted">
                {note}
              </Text>
            ))}
          </Stack>
        </Banner>
      )}
    </Stack>
  );
}
