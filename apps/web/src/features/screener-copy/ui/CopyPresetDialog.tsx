/** "Copy to my screeners": names the copy; it extends the preset at its current version (pinned) as a draft. */
import { Button, Dialog, Field, Input } from '@algotrade/ui';
import { useState } from 'react';

import { errorDetail } from '@/shared/api';

import { isScreenId } from '@/entities/screen';

import { useCopyPreset } from '../api/hooks';

export interface CopyPresetDialogProps {
  preset: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The copy exists (as a draft): open it. */
  onCopied: (id: string) => void;
}

export function CopyPresetDialog({ preset, open, onOpenChange, onCopied }: CopyPresetDialogProps) {
  const [name, setName] = useState(`my-${preset}`.slice(0, 64));
  const copy = useCopyPreset(preset);
  const invalid = name !== '' && !isScreenId(name) ? 'Use 1-64 of a-z, 0-9, _ and -.' : undefined;
  const error = invalid ?? (copy.error ? errorDetail(copy.error) : undefined);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Copy to my screeners"
      description={`Your copy extends ${preset} at its current version; change what you like, finalize when ready.`}
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
            disabled={!isScreenId(name)}
            loading={copy.isPending}
            onClick={() => {
              copy.mutate(name, {
                onSuccess: () => {
                  onCopied(name);
                },
              });
            }}
          >
            Copy
          </Button>
        </>
      }
    >
      <Field label="Name of your copy" {...(error ? { error } : {})}>
        <Input value={name} onValueChange={setName} mono autoComplete="off" spellCheck={false} />
      </Field>
    </Dialog>
  );
}
