/**
 * Step 1, Idea: the name, the thesis in one sentence, why it should last (the mechanism and why
 * it survives being known) and the sources. "More" holds the quality bar's other seven answers.
 */
import { Button, Disclosure, Field, Grid, Input, Stack, TextArea } from '@algotrade/ui';

import type { EdgeDraft } from '../model/draft';
import { useHelp } from '../model/help';
import { QUALITY_LABELS } from '../model/options';
import type { StepProps } from './step';

export interface IdeaStepProps extends StepProps {
  /** The id is chosen only for a new edge that is not saved yet. */
  chooseId: boolean;
  idError?: string | undefined;
}

export function IdeaStep({ draft, onChange, chooseId, idError }: IdeaStepProps) {
  const help = useHelp();
  const setSource = (index: number, patch: Partial<EdgeDraft['sources'][number]>) => {
    onChange({ sources: draft.sources.map((s, i) => (i === index ? { ...s, ...patch } : s)) });
  };
  return (
    <Stack gap={3}>
      <Grid columns={2} gap={3} collapse="md">
        <Field label="Name" required>
          <Input
            value={draft.name}
            onValueChange={(name) => {
              onChange({ name });
            }}
          />
        </Field>
        {chooseId && (
          <Field label="Id" error={idError} required>
            <Input
              value={draft.id}
              onValueChange={(id) => {
                onChange({ id });
              }}
              mono
              autoComplete="off"
              spellCheck={false}
            />
          </Field>
        )}
      </Grid>
      <Field label="Thesis, one sentence" required>
        <Input
          value={draft.thesis}
          onValueChange={(thesis) => {
            onChange({ thesis });
          }}
        />
      </Field>
      <Field label="Why it should last: who is forced or wrong" required>
        <TextArea
          value={draft.mechanism}
          onValueChange={(mechanism) => {
            onChange({ mechanism });
          }}
        />
      </Field>
      <Field label="Why it survives being known" required>
        <TextArea
          value={draft.persistence}
          onValueChange={(persistence) => {
            onChange({ persistence });
          }}
        />
      </Field>
      <Stack gap={2}>
        {draft.sources.map((source, index) => (
          <Grid key={index} columns={2} gap={2} collapse="md" align="start">
            <Field label={`Source ${String(index + 1)}: title`} required={index === 0}>
              <Input
                value={source.title}
                onValueChange={(title) => {
                  setSource(index, { title });
                }}
              />
            </Field>
            <Stack direction="row" gap={2} align="start">
              <Field label={`Source ${String(index + 1)}: link (https)`}>
                <Input
                  type="url"
                  value={source.url}
                  onValueChange={(url) => {
                    setSource(index, { url });
                  }}
                />
              </Field>
              {draft.sources.length > 1 && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    onChange({ sources: draft.sources.filter((_, i) => i !== index) });
                  }}
                >
                  Remove
                </Button>
              )}
            </Stack>
          </Grid>
        ))}
        <Stack direction="row">
          <Button
            variant="secondary"
            onClick={() => {
              onChange({ sources: [...draft.sources, { title: '', url: '' }] });
            }}
          >
            Add a source
          </Button>
        </Stack>
      </Stack>
      <Stack direction="row" gap={2} align="start">
        <Disclosure label="More: the rest of the quality bar">
          <Stack gap={3}>
            {Object.entries(QUALITY_LABELS).map(([key, label]) => (
              <Field key={key} label={label} required>
                <TextArea
                  value={draft.qualityBar[key] ?? ''}
                  onValueChange={(text) => {
                    onChange({ qualityBar: { ...draft.qualityBar, [key]: text } });
                  }}
                />
              </Field>
            ))}
          </Stack>
        </Disclosure>
        {help('edge_quality_bar')}
      </Stack>
    </Stack>
  );
}
