/** A feature's distribution across the universe, shaped for the Distribution component. */
import type { DistributionBin, DistributionMarker } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

/** A feature across the universe as `Query.distribution` serves it. */
export type FeatureDistribution = NonNullable<gqlTypes.FeatureDistributionQuery['distribution']>;

export function distributionBins(distribution: FeatureDistribution): DistributionBin[] {
  return distribution.histogram.map((bin) => ({ start: bin.lo, end: bin.hi, count: bin.count }));
}

const QUANTILES: readonly (readonly [number, string])[] = [
  [0.25, 'p25'],
  [0.5, 'median'],
  [0.75, 'p75'],
];

/** Quantile lines that the API returned, plus the highlighted value (the focused ticker). */
export function distributionMarkers(
  distribution: FeatureDistribution,
  highlight?: { label: string; value: number },
): DistributionMarker[] {
  const markers: DistributionMarker[] = [];
  for (const [q, label] of QUANTILES) {
    const value = distribution.quantiles.find((quantile) => quantile.q === q)?.value;
    if (value !== undefined) markers.push({ value, label });
  }
  if (highlight && Number.isFinite(highlight.value)) {
    markers.push({ ...highlight, tone: 'accent' });
  }
  return markers;
}

/** Category values with their counts (text features: sectors, liquidity classes). */
export function distributionCategories(
  distribution: FeatureDistribution | null | undefined,
): string[] {
  return (distribution?.categories ?? []).map((c) => c.value);
}
