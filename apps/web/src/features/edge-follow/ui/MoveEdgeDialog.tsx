/**
 * One dialog for every move of the user's state about an edge: Follow (with the warning when its
 * verdict is not good, and a note that following shows a copy's out-of-sample result), Reject
 * (a reason is needed), Retire, Back to researching, and Show out-of-sample (a copy's hidden
 * result; the server records that it was seen). The warnings are the server's: the verdict's
 * reason, and the labels it puts on the edge.
 */
import { Banner, Button, Dialog, Field, Input, Stack } from '@algotrade/ui';
import { useState } from 'react';

import type { Edge } from '@/entities/edge';
import { errorDetail } from '@/shared/api';

import { useMoveEdge } from '../api/hooks';
import { asksReason, MOVE_LABELS, TARGET, warnsFollow, type Move } from '../model/moves';

export interface MoveEdgeDialogProps {
  edge: Edge;
  move: Move;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MoveEdgeDialog({ edge, move, open, onOpenChange }: MoveEdgeDialogProps) {
  const [reason, setReason] = useState('');
  const mover = useMoveEdge(edge.id);
  const needsReason = move === 'reject' && reason.trim() === '';
  const close = () => {
    onOpenChange(false);
  };
  const target = TARGET[move];
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`${MOVE_LABELS[move]} · ${edge.name}`}
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={needsReason}
            loading={mover.isPending}
            onClick={() => {
              mover.mutate(
                {
                  ...(target ? { state: target } : {}),
                  reason: reason.trim(),
                  revealOos: move === 'reveal',
                },
                { onSuccess: close },
              );
            }}
          >
            {MOVE_LABELS[move]}
          </Button>
        </>
      }
    >
      <Stack gap={3}>
        {move === 'follow' && warnsFollow(edge) && (
          <Banner
            tone="warning"
            title={edge.verdict.verdict === 'not_working' ? 'Not working' : 'Not enough data'}
          >
            {edge.verdict.rationale}
          </Banner>
        )}
        {(move === 'reveal' || (move === 'follow' && edge.oosHidden)) && (
          <Banner tone="info">The out-of-sample result is shown and cannot be hidden again.</Banner>
        )}
        {asksReason(move) && (
          <Field label={move === 'reject' ? 'Why' : 'Why (optional)'}>
            <Input value={reason} onValueChange={setReason} autoComplete="off" />
          </Field>
        )}
        {mover.error && <Banner tone="negative">{errorDetail(mover.error)}</Banner>}
      </Stack>
    </Dialog>
  );
}
