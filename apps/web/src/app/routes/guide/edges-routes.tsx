/**
 * The Guide's Edges route components (`/guide/edges`, `/guide/edges/m/$mechanism`,
 * `/guide/edges/$id`), loaded on first visit: they and their navigation to the live Edges page
 * live here, outside the entry chunk, as the edge builder's route does. The route's loader
 * starts the Guide's shared reads through the page module this file re-exports.
 */
import { useNavigate, useParams } from '@tanstack/react-router';

import { EDGES_PAGE_PATH } from '@/entities/guide';
import { GuideEdgePage, GuideEdgesPage, GuideMechanismPage } from '@/pages/guide';

export { prefetchGuideReads } from '@/pages/guide';

export function EdgesIndexRoute() {
  const navigate = useNavigate();
  return <GuideEdgesPage onOpenEdgesPage={() => void navigate({ to: EDGES_PAGE_PATH })} />;
}

export function MechanismRoute() {
  const { mechanism } = useParams({ strict: false });
  return <GuideMechanismPage id={mechanism ?? ''} />;
}

export function EdgeRoute() {
  const { id } = useParams({ strict: false });
  const navigate = useNavigate();
  return (
    <GuideEdgePage
      id={id ?? ''}
      onSeeEvidence={() => void navigate({ to: EDGES_PAGE_PATH, search: { edge: id ?? '' } })}
    />
  );
}
