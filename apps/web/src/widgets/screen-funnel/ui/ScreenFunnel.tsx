/**
 * The funnel of the gating rules: the universe, then how many rows remain after each hard or
 * soft criterion (a near miss stays in), each named from its current rule. Rows with missing data
 * never pass and are listed apart.
 */
import { BarList, Panel, Text } from '@algotrade/ui';

import { byName, useFeatureCatalogue } from '@/entities/feature';
import {
  describeCriterion,
  previewPanelState,
  useScreenerBuilder,
} from '@/features/screener-builder';

export function ScreenFunnel() {
  const { preview, criteria } = useScreenerBuilder();
  const features = byName(useFeatureCatalogue().data ?? []);
  // A step reads as the criterion as it is now, not as a label stored with an older threshold.
  const described = new Map(
    criteria.map((c) => [c.id, describeCriterion(c, features.get(c.field))]),
  );
  const funnel = preview.data?.funnel ?? [];
  const universe = funnel[0]?.entering ?? preview.data?.coverage.selected ?? 0;
  const items = [
    { id: 'universe', label: 'Universe', value: universe },
    ...funnel.map((step) => ({
      id: step.criterion_id,
      label: described.get(step.criterion_id) ?? step.label ?? step.criterion_id,
      value: step.remaining,
    })),
  ];
  return (
    <Panel
      title="Funnel (gating criteria)"
      state={previewPanelState(preview)}
      loadingLabel="Running the preview…"
      emptyMessage="Add a complete criterion to see the funnel."
      errorMessage={preview.error ?? 'The preview failed.'}
      footer={
        preview.data
          ? `Skipped (missing data, never passed): ${preview.data.summary.skipped.toLocaleString('en-US')}`
          : undefined
      }
    >
      {preview.data && funnel.length === 0 ? (
        <Text size="sm" tone="muted">
          No hard or soft criterion: every row is screened.
        </Text>
      ) : (
        <BarList label="Funnel (gating criteria)" items={items} max={universe} layout="stacked" />
      )}
    </Panel>
  );
}
