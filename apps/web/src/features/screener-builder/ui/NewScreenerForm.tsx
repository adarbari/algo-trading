/**
 * Start a screener: name it (1-64 of a-z, 0-9, _ and -) and pick the universe it screens; a blank
 * draft is saved under the name and the Builder opens it.
 */
import { Button, Field, Input, Select, Stack } from '@algotrade/ui';
import { useState } from 'react';

import { errorDetail } from '@/shared/api';

import { blankDocument, isScreenId, useScreeners } from '@/entities/screen';

import { useCreateScreener } from '../api/hooks';

export interface NewScreenerFormProps {
  /** The screener was created: open it. */
  onCreated: (id: string) => void;
  onCancel: () => void;
}

/** Offered when no screener names a universe yet: the site's liquid optionable one. */
const FALLBACK_SELECTION = 'liquid_optionable';

export function NewScreenerForm({ onCreated, onCancel }: NewScreenerFormProps) {
  const screeners = useScreeners();
  const selections = [
    ...new Set(
      (screeners.data ?? []).flatMap((s) =>
        s.selection && s.selection !== 'inline' ? [s.selection] : [],
      ),
    ),
  ];
  if (selections.length === 0) selections.push(FALLBACK_SELECTION);
  const [id, setId] = useState('');
  const [chosen, setSelection] = useState<string | null>(null);
  const selection = chosen ?? selections[0] ?? FALLBACK_SELECTION;
  const create = useCreateScreener();
  const taken = (screeners.data ?? []).some((s) => s.config_id === id);
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
      { id, document: blankDocument(id, selection) },
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
      <Field label="Universe" hint="The selection this screener runs over">
        {selections.length > 0 ? (
          <Select
            options={selections.map((s) => ({ value: s, label: s }))}
            value={selection}
            onValueChange={setSelection}
          />
        ) : (
          <Input value={selection} onValueChange={setSelection} mono />
        )}
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
