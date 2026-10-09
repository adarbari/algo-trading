/**
 * "Copy to my screeners": names the copy; it extends the preset at its current version (pinned)
 * as a draft. With `own`, the source is one of the user's screeners and the copy starts from its
 * document ("Duplicate").
 */
import { Button, Dialog, Field, Input } from '@algotrade/ui';
import { useState } from 'react';

import { errorDetail } from '@/shared/api';

import { isScreenId } from '@/entities/screen';

import { useCopyPreset, useDuplicateScreener, useSourceDocument } from '../api/hooks';

export interface CopyPresetDialogProps {
  preset: string;
  /** `preset` is one of the user's own screeners, not a site preset. */
  own?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The copy exists (as a draft): open it. */
  onCopied: (id: string) => void;
}

export function CopyPresetDialog({
  preset,
  own = false,
  open,
  onOpenChange,
  onCopied,
}: CopyPresetDialogProps) {
  const [name, setName] = useState((own ? `${preset}-copy` : `my-${preset}`).slice(0, 64));
  const fromPreset = useCopyPreset(preset);
  const fromOwn = useDuplicateScreener();
  const source = useSourceDocument(preset, own);
  const copy = own ? fromOwn : fromPreset;
  const invalid = name !== '' && !isScreenId(name) ? 'Use 1-64 of a-z, 0-9, _ and -.' : undefined;
  const error = invalid ?? (copy.error ? errorDetail(copy.error) : undefined);
  const done = {
    onSuccess: () => {
      onCopied(name);
    },
  };
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={own ? 'Duplicate screener' : 'Copy to my screeners'}
      description={
        own
          ? `Your copy starts from ${preset}; change what you like, finalize when ready.`
          : `Your copy extends ${preset} at its current version; change what you like, finalize when ready.`
      }
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
            disabled={!isScreenId(name) || (own && !source.document)}
            loading={copy.isPending}
            onClick={() => {
              if (!own) fromPreset.mutate(name, done);
              else if (source.document) fromOwn.mutate({ name, source: source.document }, done);
            }}
          >
            {own ? 'Duplicate' : 'Copy'}
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
