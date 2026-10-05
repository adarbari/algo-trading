/** "Save view as": names the current columns, sort and decisions as one of your views of this table. */
import { Button, Dialog, Field, Input } from '@algotrade/ui';
import { useState } from 'react';

export interface SaveViewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Names already in use (saving under one replaces it). */
  taken: readonly string[];
  saving: boolean;
  onSave: (name: string) => void;
  /** The API's reason it was refused, if any. */
  error?: string | undefined;
}

const MAX_NAME = 40;

export function SaveViewDialog({
  open,
  onOpenChange,
  taken,
  saving,
  onSave,
  error,
}: SaveViewDialogProps) {
  const [name, setName] = useState('');
  const trimmed = name.trim();
  const problem = trimmed.length > MAX_NAME ? `Use at most ${String(MAX_NAME)} characters.` : error;
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Save view as"
      description="Your columns, sort and decisions, kept as your own view of this table. Saving under an existing name replaces it."
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={trimmed === '' || trimmed.length > MAX_NAME}
            loading={saving}
            onClick={() => {
              onSave(trimmed);
            }}
          >
            {taken.includes(trimmed) ? 'Replace' : 'Save'}
          </Button>
        </>
      }
    >
      <Field label="Name of the view" {...(problem ? { error: problem } : {})}>
        <Input value={name} onValueChange={setName} autoComplete="off" spellCheck={false} />
      </Field>
    </Dialog>
  );
}
