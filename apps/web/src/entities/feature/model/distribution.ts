/** A feature's distribution across the universe, shaped for the Distribution component. */
import type { DistributionBin, DistributionMarker } from '@algotrade/ui';

import type { components } from '@/shared/api';

export type FeatureDistribution = components['schemas']['Distribution'];

export function distributionBins(distribution: FeatureDistribution): DistributionBin[] {
  return distribution.histogram.map((bin) => ({ start: bin.lo, end: bin.hi, count: bin.count }));
}

const QUANTILES: readonly (readonly [string, string])[] = [
  ['0.25', 'p25'],
  ['0.5', 'median'],
  ['0.75', 'p75'],
];

/** Quantile lines that the API returned, plus the highlighted value (the focused ticker). */
export function distributionMarkers(
  distribution: FeatureDistribution,
  highlight?: { label: string; value: number },
): DistributionMarker[] {
  const markers: DistributionMarker[] = [];
  for (const [key, label] of QUANTILES) {
    const value = distribution.quantiles[key];
    if (value !== undefined) markers.push({ value, label });
  }
  if (highlight && Number.isFinite(highlight.value)) {
    markers.push({ ...highlight, tone: 'accent' });
  }
  return markers;
}

/** Category values with their counts (text features: sectors, liquidity classes). */
export function distributionCategories(distribution: FeatureDistribution | undefined): string[] {
  return (distribution?.categories ?? []).map((c) => c.value);
}
