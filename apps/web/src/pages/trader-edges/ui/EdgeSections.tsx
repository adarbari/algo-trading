/**
 * Everything below an edge's verdict, in one chunk (the page lazy-loads it once): Evidence, How
 * sure, Where it worked, the comparison of a copy, the live record (once the edge has one), the
 * definition and the details. Each section is a `LazySection`, so it renders and reads its data
 * when it nears the viewport; their ids are what the page's navigation scrolls to.
 */
import type { Edge } from '@/entities/edge';
import { EdgeCompare, EdgeDefinition, EdgeDetails, EdgeLive } from '@/widgets/edge-detail';
import { EdgeDiagnostics } from '@/widgets/edge-diagnostics';
import { EdgeEvidence } from '@/widgets/edge-evidence';
import { EdgePerformance } from '@/widgets/edge-performance';
import { EdgeSureness } from '@/widgets/edge-sureness';
import { EdgeTrades } from '@/widgets/edge-trades';

import { EdgeSection } from './EdgeSection';

export interface EdgeSectionsProps {
  edge: Edge;
  /** The edge has a live record: its section is shown. */
  hasLive: boolean;
}

export function EdgeSections({ edge, hasLive }: EdgeSectionsProps) {
  return (
    <>
      <EdgeSection id="edge-evidence" label="Evidence" size="xl">
        <EdgeEvidence edgeId={edge.id} verdict={edge.verdict} />
      </EdgeSection>
      <EdgeSection id="edge-sure" label="How sure">
        <EdgeSureness edgeId={edge.id} verdict={edge.verdict} />
      </EdgeSection>
      <EdgeSection id="edge-where" label="Where it worked">
        <EdgePerformance edgeId={edge.id} verdict={edge.verdict} />
      </EdgeSection>
      {edge.mine && (
        <EdgeSection id="edge-compare" label="Compare versions" size="md">
          <EdgeCompare edgeId={edge.id} />
        </EdgeSection>
      )}
      {hasLive && (
        <EdgeSection id="edge-live" label="Live record">
          <EdgeLive edgeId={edge.id} />
        </EdgeSection>
      )}
      <EdgeSection id="edge-trades" label="Trades">
        <EdgeTrades edgeId={edge.id} />
      </EdgeSection>
      <EdgeSection id="edge-definition" label="Definition">
        <EdgeDefinition edge={edge} />
      </EdgeSection>
      <EdgeSection id="edge-details" label="Details" size="sm">
        <EdgeDetails edge={edge}>
          <EdgeDiagnostics edgeId={edge.id} />
        </EdgeDetails>
      </EdgeSection>
    </>
  );
}
