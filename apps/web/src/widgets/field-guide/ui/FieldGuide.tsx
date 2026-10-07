/**
 * The field guide: a narrow sidebar to find a catalogue field (search, themes, the theme's
 * fields), and the field's page beside it (stacked below at phone width): what the number means
 * first, large, then where today's values sit across the universe, one name over the last year,
 * the criterion per intent, when the number lies and how it is computed. The choice (theme,
 * field, symbol) belongs to the caller, so a field is a link.
 */
import { EmptyState, ErrorState, Grid, Skeleton, Stack } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import {
  guideThemes,
  resolveSelection,
  searchFields,
  themeFields,
  themeOf,
  useFeatureCatalogue,
  type CatalogueFeature,
} from '@/entities/feature';

import { CaveatsPanel } from './CaveatsPanel';
import { ComputedPanel } from './ComputedPanel';
import { CriteriaPanel } from './CriteriaPanel';
import { FieldHero } from './FieldHero';
import { FieldSidebar } from './FieldSidebar';
import { SeriesPanel } from './SeriesPanel';
import { UniversePanel } from './UniversePanel';

export interface FieldGuideProps {
  /** The theme and field the URL asks for (either may be absent or unknown). */
  theme: string | undefined;
  field: string | undefined;
  /** The symbol the URL asks for; absent: `defaultSymbol`. */
  symbol: string | undefined;
  /** The Explore selection: the symbol shown when the URL has none. */
  defaultSymbol: string | null;
  onThemeChange: (theme: string) => void;
  /** A field was chosen: its name and the theme it is in. */
  onFieldChange: (choice: { theme: string; field: string }) => void;
  onSymbolChange: (symbol: string) => void;
  /** Opens the Screener Builder (it takes no criterion by URL yet). */
  onAddToScreen: () => void;
}

/** The detail of one field; remounted per field so the criterion shown starts at its first. */
function FieldDetail({
  feature,
  symbol,
  onSymbolChange,
  onAddToScreen,
}: {
  feature: CatalogueFeature;
  symbol: string | null;
  onSymbolChange: (symbol: string) => void;
  onAddToScreen: () => void;
}) {
  const [useIndex, setUseIndex] = useState(0);
  const uses = feature.guide?.uses ?? [];
  return (
    <Stack gap={4}>
      <FieldHero feature={feature} />
      <Grid columns={2} gap={4} collapse="lg" align="start">
        <UniversePanel feature={feature} useIndex={useIndex} onUseChange={setUseIndex} />
        <SeriesPanel
          feature={feature}
          symbol={symbol}
          onSymbolChange={onSymbolChange}
          use={uses[useIndex]}
        />
      </Grid>
      <CriteriaPanel uses={uses} onAddToScreen={onAddToScreen} />
      <Grid columns={2} gap={4} collapse="lg" align="start">
        {feature.guide && feature.guide.caveats.length > 0 && (
          <CaveatsPanel caveats={feature.guide.caveats} />
        )}
        <ComputedPanel feature={feature} />
      </Grid>
    </Stack>
  );
}

export function FieldGuide({
  theme,
  field,
  symbol,
  defaultSymbol,
  onThemeChange,
  onFieldChange,
  onSymbolChange,
  onAddToScreen,
}: FieldGuideProps) {
  const catalogue = useFeatureCatalogue();
  const [query, setQuery] = useState('');
  const all = catalogue.data;
  const selection = useMemo(
    () => (all ? resolveSelection(all, { theme, field }) : null),
    [all, theme, field],
  );
  const matches = useMemo(() => searchFields(all ?? [], query), [all, query]);
  const themes = useMemo(() => {
    const counted = new Map(guideThemes(matches).map((t) => [t.name, t.count]));
    return guideThemes(all ?? []).map((t) => ({ name: t.name, count: counted.get(t.name) ?? 0 }));
  }, [all, matches]);

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
  if (!selection) return <EmptyState bordered title="The catalogue has no fields." />;

  return (
    <Grid columns="sidebar-start" gap={4} collapse="md" align="start">
      <FieldSidebar
        query={query}
        onQueryChange={setQuery}
        themes={themes}
        theme={selection.theme}
        onThemeChange={onThemeChange}
        fields={themeFields(matches, selection.theme)}
        field={selection.field?.name ?? null}
        onFieldChange={(name) => {
          const picked = all?.find((f) => f.name === name);
          if (picked) onFieldChange({ theme: themeOf(picked), field: picked.name });
        }}
      />
      {selection.field ? (
        <FieldDetail
          key={selection.field.name}
          feature={selection.field}
          symbol={symbol ?? defaultSymbol}
          onSymbolChange={onSymbolChange}
          onAddToScreen={onAddToScreen}
        />
      ) : (
        <EmptyState bordered title="No field in this theme." />
      )}
    </Grid>
  );
}
