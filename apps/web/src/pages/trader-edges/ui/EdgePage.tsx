/**
 * One edge's page (the chosen edge in place of the list): the head with the verdict and what
 * would change it, then a sticky navigation and the sections in reading order, each loaded when
 * it nears the viewport: Evidence (the curve and the figures), How sure (deciles, robustness,
 * decay), Where it worked (year by year, drawdown), the Live record (once the edge has one), the
 * definition and the details. The page holds the edge the list read; each section reads its own
 * numbers (ADR 0037). Every word and number comes from the server.
 */
import {
  EmptyState,
  ErrorState,
  SectionNav,
  Skeleton,
  Stack,
  type SectionNavItem,
} from '@algotrade/ui';
import { Suspense } from 'react';

import { useEdgeLiveStates, useEdges } from '@/entities/edge';
import { EdgeHeader } from '@/widgets/edge-detail';
import { lazyPage } from '@/shared/lib/lazy';

// One lazy chunk for everything below the verdict: each lazy chunk adds its id to the entry's
// dependency lists (a budget that only shrinks), and each section still renders when in view.
const EdgeSections = lazyPage(() => import('./EdgeSections'), 'EdgeSections');

export interface EdgePageProps {
  /** The chosen edge's id (from the URL). */
  id: string;
  /** Back to the edges list. */
  onBack: () => void;
  /** Open the builder on one of the user's edges (a copy was made, or Edit). */
  onEdit: (id: string) => void;
}

export function EdgePage({ id, onBack, onEdit }: EdgePageProps) {
  const edges = useEdges();
  const live = useEdgeLiveStates().data?.find((s) => s.edgeId === id);
  const edge = edges.data?.find((e) => e.id === id);
  if (edges.isPending) return <Skeleton variant="rect" label="Loading edge" />;
  if (edges.isError && !edges.data) {
    return <ErrorState title="The edge failed to load." onRetry={() => void edges.refetch()} />;
  }
  if (!edge) return <EmptyState title={`No edge ${id}`} bordered />;
  const hasLive = live != null && live.state !== 'no_trades';
  const sections: SectionNavItem[] = [
    { id: 'edge-evidence', label: 'Evidence' },
    { id: 'edge-sure', label: 'How sure' },
    { id: 'edge-where', label: 'Where it worked' },
    ...(hasLive ? [{ id: 'edge-live', label: 'Live record' }] : []),
    { id: 'edge-definition', label: 'Definition' },
    { id: 'edge-details', label: 'Details' },
  ];
  return (
    <Stack gap={4}>
      <EdgeHeader edge={edge} onBack={onBack} onEdit={onEdit} />
      <SectionNav items={sections} aria-label="Sections of this edge" />
      <Suspense fallback={<Skeleton variant="rect" height="lg" label="Loading the sections" />}>
        <EdgeSections edge={edge} hasLive={hasLive} />
      </Suspense>
    </Stack>
  );
}
