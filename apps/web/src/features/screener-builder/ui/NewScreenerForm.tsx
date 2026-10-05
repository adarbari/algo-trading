/**
 * Start a screener: name it (1-64 of a-z, 0-9, _ and -); a draft with the base gates is saved under
 * the name and the Builder opens it.
 */
import { Button, Field, Input, Stack } from '@algotrade/ui';
import { useState } from 'react';

import { errorDetail } from '@/shared/api';

import { blankDocument, isScreenId, useMyScreeners, useScreeners } from '@/entities/screen';

import { useCreateScreener } from '../api/hooks';

export interface NewScreenerFormProps {
  /** The screener was created: open it. */
  onCreated: (id: string) => void;
  onCancel: () => void;
}

export function NewScreenerForm({ onCreated, onCancel }: NewScreenerFormProps) {
  const screeners = useScreeners();
  const mine = useMyScreeners();
  const [id, setId] = useState('');
  const create = useCreateScreener();
  const taken =
    (screeners.data ?? []).some((s) => s.configId === id && s.scope !== 'site') ||
    (mine.data ?? []).some((s) => s.screenerId === id);
  const idError =
    id !== '' && !isScreenId(id)
      ? 'Use 1-64 of a-z, 0-9, _ and -.'
      : taken
        ? 'A screener with this name already exists.'
        : undefined;
  const conflict = create.error ? errorDetail(create.error) : undefined;
  const canCreate = isScreenId(id) && !taken;
  const submit = () => {
    create.mutate(
      { id, document: blankDocument(id) },
      {
        onSuccess: () => {
          onCreated(id);
        },
      },
    );
  };
  return (
    <Stack gap={3}>
      <Field
        label="Name"
        hint="Becomes the screener's id, e.g. high-iv-near-extreme"
        error={idError ?? conflict}
      >
        <Input
          value={id}
          onValueChange={setId}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && canCreate) submit();
          }}
          mono
          autoComplete="off"
          spellCheck={false}
        />
      </Field>
      <Stack direction="row" gap={2}>
        <Button variant="primary" onClick={submit} disabled={!canCreate} loading={create.isPending}>
          Create draft
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </Stack>
    </Stack>
  );
}
