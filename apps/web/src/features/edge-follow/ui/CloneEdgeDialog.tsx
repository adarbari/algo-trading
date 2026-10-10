/**
 * "Clone" and "New version": names the user's own copy of an edge; the copy extends it (changes
 * stay theirs, the edge keeps its own result; a version is a trial that would replace it) and
 * opens in the builder when it is made.
 */
import { Button, Dialog, Field, Input } from '@algotrade/ui';
import { useState } from 'react';

import { errorDetail } from '@/shared/api';

import { useCopyEdge } from '../api/hooks';
import { isEdgeId } from '../model/moves';

export interface CloneEdgeDialogProps {
  /** The edge to copy. */
  edgeId: string;
  /** A new version of a followed edge, not a plain copy. */
  asVersion?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The copy exists: open it. */
  onCloned: (id: string) => void;
}

export function CloneEdgeDialog({
  edgeId,
  asVersion = false,
  open,
  onOpenChange,
  onCloned,
}: CloneEdgeDialogProps) {
  const [name, setName] = useState((asVersion ? `${edgeId}-v2` : `my-${edgeId}`).slice(0, 64));
  const copy = useCopyEdge(edgeId, asVersion);
  const invalid = name !== '' && !isEdgeId(name) ? 'Use 1-64 of a-z, 0-9, _ and -.' : undefined;
  const error = invalid ?? (copy.error ? errorDetail(copy.error) : undefined);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={asVersion ? 'New version' : 'Clone edge'}
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
            disabled={!isEdgeId(name)}
            loading={copy.isPending}
            onClick={() => {
              copy.mutate(name, {
                onSuccess: () => {
                  onCloned(name);
                },
              });
            }}
          >
            {asVersion ? 'Create version' : 'Clone'}
          </Button>
        </>
      }
    >
      <Field
        label={asVersion ? 'Name of the new version' : 'Name of your copy'}
        {...(error ? { error } : {})}
      >
        <Input value={name} onValueChange={setName} mono autoComplete="off" spellCheck={false} />
      </Field>
    </Dialog>
  );
}
