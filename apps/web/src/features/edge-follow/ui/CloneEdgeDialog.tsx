/**
 * "Clone": names the user's own copy of an edge; the copy extends it (changes stay theirs, the
 * edge keeps its own result) and opens when it is made.
 */
import { Button, Dialog, Field, Input } from '@algotrade/ui';
import { useState } from 'react';

import { errorDetail } from '@/shared/api';

import { useCopyEdge } from '../api/hooks';
import { isEdgeId } from '../model/moves';

export interface CloneEdgeDialogProps {
  /** The edge to copy. */
  edgeId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The copy exists: open it. */
  onCloned: (id: string) => void;
}

export function CloneEdgeDialog({ edgeId, open, onOpenChange, onCloned }: CloneEdgeDialogProps) {
  const [name, setName] = useState(`my-${edgeId}`.slice(0, 64));
  const copy = useCopyEdge(edgeId);
  const invalid = name !== '' && !isEdgeId(name) ? 'Use 1-64 of a-z, 0-9, _ and -.' : undefined;
  const error = invalid ?? (copy.error ? errorDetail(copy.error) : undefined);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Clone edge"
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
            Clone
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
