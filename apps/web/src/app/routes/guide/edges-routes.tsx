/**
 * The Guide's Edges route components (`/guide/edges`, `/guide/edges/m/$mechanism`,
 * `/guide/edges/$id`, one splat route), loaded on first visit: they and their navigation to the live Edges page
 * live here, outside the entry chunk, as the edge builder's route does. The route's loader
 * starts the Guide's shared reads through the page module this file re-exports.
 */
import { useNavigate, useParams } from '@tanstack/react-router';

import { EDGES_PAGE_PATH } from '@/entities/guide';
import { GuideEdgePage, GuideEdgesPage, GuideMechanismPage } from '@/pages/guide';

export { prefetchGuideReads } from '@/pages/guide';

function EdgesIndexRoute() {
  const navigate = useNavigate();
  return <GuideEdgesPage onOpenEdgesPage={() => void navigate({ to: EDGES_PAGE_PATH })} />;
}

function MechanismRoute({ id }: { id: string }) {
  return <GuideMechanismPage id={id} />;
}

function EdgeRoute({ id }: { id: string }) {
  const navigate = useNavigate();
  return (
    <GuideEdgePage
      id={id}
      onSeeEvidence={() => void navigate({ to: EDGES_PAGE_PATH, search: { edge: id } })}
    />
  );
}

/** The one route of the section: the splat is "" (the index), "m/<mechanism>" or an edge id. */
export function EdgesRoutes() {
  const { _splat } = useParams({ strict: false });
  const [first = '', second = ''] = (_splat ?? '').split('/');
  if (first === '') return <EdgesIndexRoute />;
  if (first === 'm') return <MechanismRoute id={decodeURIComponent(second)} />;
  return <EdgeRoute id={decodeURIComponent(first)} />;
}
