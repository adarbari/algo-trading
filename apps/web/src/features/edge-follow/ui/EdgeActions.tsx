/**
 * The actions of an edge's page: Clone, the moves its state allows (Follow, Reject, Retire, Back
 * to researching), Show out-of-sample for a copy whose result is withheld, and for an admin
 * Publish (the edge as one TOML file to land in the site's config by pull request). The API
 * decides what is allowed and which warnings are kept; the buttons only ask.
 */
import { Button, saveTextFile, Stack, useToast } from '@algotrade/ui';
import { Suspense, useState } from 'react';

import type { Edge } from '@/entities/edge';
import { useViewer } from '@/entities/viewer';

import { publishedDocument } from '../api/hooks';
import { canReveal, MOVE_LABELS, movesFrom, type Move } from '../model/moves';
import { lazyPage } from '@/shared/lib/lazy';

// The dialogs load when first opened: most visits to an edge never open one.
const CloneEdgeDialog = lazyPage(() => import('./CloneEdgeDialog'), 'CloneEdgeDialog');
const MoveEdgeDialog = lazyPage(() => import('./MoveEdgeDialog'), 'MoveEdgeDialog');

export interface EdgeActionsProps {
  edge: Edge;
  /** A copy or a new version was made, or Edit was chosen: open it in the builder. */
  onEdit: (id: string) => void;
}

export function EdgeActions({ edge, onEdit }: EdgeActionsProps) {
  const viewer = useViewer();
  const toast = useToast();
  const [cloning, setCloning] = useState<'clone' | 'version' | null>(null);
  const [move, setMove] = useState<Move | null>(null);
  const [publishing, setPublishing] = useState(false);
  const moves: Move[] = [
    ...movesFrom(edge.state),
    ...(canReveal(edge) ? (['reveal'] as const) : []),
  ];
  const publish = async () => {
    setPublishing(true);
    try {
      const text = await publishedDocument(edge.id);
      if (text === null) throw new Error('The edge has no document to publish');
      saveTextFile(`${edge.id}.toml`, text);
    } catch (error) {
      toast.show({
        tone: 'negative',
        title: 'The edge could not be published',
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setPublishing(false);
    }
  };
  return (
    <>
      <Stack direction="row" gap={2} align="center" wrap>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setCloning('clone');
          }}
        >
          Clone
        </Button>
        {edge.state === 'following' && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setCloning('version');
            }}
          >
            New version
          </Button>
        )}
        {edge.mine && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              onEdit(edge.id);
            }}
          >
            Edit
          </Button>
        )}
        {moves.map((m) => (
          <Button
            key={m}
            size="sm"
            variant={m === 'follow' ? 'primary' : 'secondary'}
            onClick={() => {
              setMove(m);
            }}
          >
            {MOVE_LABELS[m]}
          </Button>
        ))}
        {viewer.data?.role === 'admin' && edge.mine && (
          <Button size="sm" variant="secondary" loading={publishing} onClick={() => void publish()}>
            Publish site-wide
          </Button>
        )}
      </Stack>
      <Suspense fallback={null}>
        {cloning && (
          <CloneEdgeDialog
            edgeId={edge.id}
            asVersion={cloning === 'version'}
            open
            onOpenChange={(open) => {
              if (!open) setCloning(null);
            }}
            onCloned={(id) => {
              setCloning(null);
              onEdit(id);
            }}
          />
        )}
        {move && (
          <MoveEdgeDialog
            edge={edge}
            move={move}
            open
            onOpenChange={(open) => {
              if (!open) setMove(null);
            }}
          />
        )}
      </Suspense>
    </>
  );
}
