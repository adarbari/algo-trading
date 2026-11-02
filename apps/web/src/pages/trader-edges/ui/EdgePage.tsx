/**
 * One setup's page (the chosen edge in place of the library): the head with the verdict and what
 * would change it, then a sticky navigation and the sections in reading order, each loaded when
 * it nears the viewport: the rules, how it has done, when it fails, before you act and Dig deeper.
 * The page reads this one edge (so one verdict is judged); each section reads its own numbers
 * (ADR 0037). Every word and number comes from the server.
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

import { useEdge, useEdgeLiveStates } from '@/entities/edge';
import { EdgeHeader } from '@/widgets/setup-head';
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
  const edges = useEdge(id);
  const live = useEdgeLiveStates().data?.find((s) => s.edgeId === id);
  const edge = edges.data;
  if (edges.isPending) return <Skeleton variant="rect" label="Loading setup" />;
  if (edges.isError && !edges.data) {
    return <ErrorState title="The setup failed to load." onRetry={() => void edges.refetch()} />;
  }
  if (!edge) return <EmptyState title={`No setup ${id}`} bordered />;
  const sections: SectionNavItem[] = [
    { id: 'setup-rules', label: 'The rules' },
    { id: 'setup-record', label: 'How it has done' },
    { id: 'setup-fails', label: 'When it fails' },
    { id: 'setup-before', label: 'Before you act' },
    { id: 'setup-deeper', label: 'Dig deeper' },
  ];
  return (
    <Stack gap={4}>
      <EdgeHeader edge={edge} onBack={onBack} onEdit={onEdit} />
      <SectionNav items={sections} aria-label="Sections of this setup" />
      <Suspense fallback={<Skeleton variant="rect" height="lg" label="Loading the sections" />}>
        <EdgeSections edge={edge} live={live} />
      </Suspense>
    </Stack>
  );
}
