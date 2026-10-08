/**
 * A field's Guide page body (ADR 0051, docs/ui/guide.md section 3), the sections in a fixed
 * order, each anchored for the "On this page" list: the header and what the number means, its
 * spread across the universe, the criterion per intent (with Add to Builder), when it lies and
 * the situations that fool it, how it is computed, related fields and the playbooks that use
 * it, one name's history with a way into Explore, and the sources. The field comes from the
 * catalogue; what the server derives for it (its reads and caveats with the field names linked,
 * related, playbooks, situations) from `guideField`, the plain text standing in while it loads.
 */
import { DocSection, EmptyState, ErrorState, Skeleton, Stack } from '@algotrade/ui';
import { useState } from 'react';

import { byName, useFeatureCatalogue, type CatalogueFeature } from '@/entities/feature';
import { useGuideField } from '@/entities/guide';

import { CaveatsPanel } from './CaveatsPanel';
import { ComputedPanel } from './ComputedPanel';
import { CriteriaPanel } from './CriteriaPanel';
import { FieldHero } from './FieldHero';
import { RelatedPanel } from './RelatedPanel';
import { SeriesPanel } from './SeriesPanel';
import { SourcesPanel } from './SourcesPanel';
import { UniversePanel } from './UniversePanel';

export interface GuideFieldProps {
  /** The catalogue name the URL asks for. */
  name: string;
  /** Opens the Screener Builder (it takes no criterion by URL yet). */
  onAddToBuilder: () => void;
}

/** The sections of one field; remounted per field so the criterion shown starts at its first. */
function FieldSections({
  feature,
  onAddToBuilder,
}: {
  feature: CatalogueFeature;
  onAddToBuilder: () => void;
}) {
  const [useIndex, setUseIndex] = useState(0);
  const [symbol, setSymbol] = useState<string | null>(null);
  const guide = useGuideField(feature.name);
  const uses = feature.guide?.uses ?? [];
  const caveats =
    guide.data?.caveatsLinked ??
    (feature.guide?.caveats ?? []).map((text) => ({ segments: [{ text }] }));
  const situations = guide.data?.situations ?? [];
  return (
    <Stack gap={6}>
      <DocSection id="reads">
        <FieldHero feature={feature} readsLinked={guide.data?.readsLinked} />
      </DocSection>
      <DocSection id="universe">
        <UniversePanel feature={feature} useIndex={useIndex} onUseChange={setUseIndex} />
      </DocSection>
      <DocSection id="use">
        <CriteriaPanel uses={uses} onAddToBuilder={onAddToBuilder} />
      </DocSection>
      <DocSection id="lies">
        <CaveatsPanel caveats={caveats} situations={situations} />
      </DocSection>
      <DocSection id="computed">
        <ComputedPanel feature={feature} />
      </DocSection>
      <DocSection id="related">
        <RelatedPanel
          related={guide.data?.related ?? []}
          playbooks={guide.data?.playbooks ?? []}
          state={guide.isError ? 'error' : guide.isPending ? 'loading' : 'ready'}
          onRetry={() => void guide.refetch()}
        />
      </DocSection>
      <DocSection id="ticker">
        <SeriesPanel
          feature={feature}
          symbol={symbol}
          onSymbolChange={setSymbol}
          use={uses[useIndex]}
        />
      </DocSection>
      <DocSection id="sources">
        <SourcesPanel sources={feature.guide?.sources ?? []} />
      </DocSection>
    </Stack>
  );
}

export function GuideField({ name, onAddToBuilder }: GuideFieldProps) {
  const catalogue = useFeatureCatalogue();
  if (catalogue.isError) {
    return (
      <ErrorState
        title="The field catalogue failed to load."
        onRetry={() => void catalogue.refetch()}
      />
    );
  }
  if (catalogue.isPending)
    return <Skeleton variant="rect" height="lg" label="Loading the field catalogue" />;
  const feature = byName(catalogue.data).get(name);
  if (!feature) {
    return (
      <EmptyState
        bordered
        title="No such field"
        description={`The catalogue has no field called ${name}.`}
      />
    );
  }
  return <FieldSections key={feature.name} feature={feature} onAddToBuilder={onAddToBuilder} />;
}
