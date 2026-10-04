/**
 * Where the threshold sits among the universe: the field's histogram (latest session) with the
 * quantiles and the threshold marked. Loaded only when opened.
 */
import { Distribution, Text } from '@algotrade/ui';

import {
  distributionBins,
  distributionMarkers,
  featureFormat,
  isNumericFeature,
  useFeatureDistribution,
  type CatalogueFeature,
} from '@/entities/feature';

export function ThresholdDistribution({
  feature,
  threshold,
}: {
  feature: CatalogueFeature;
  threshold: number | null;
}) {
  const distribution = useFeatureDistribution(feature.name);
  if (!isNumericFeature(feature)) {
    return (
      <Text size="sm" tone="muted">
        The distribution is shown for numeric features.
      </Text>
    );
  }
  const data = distribution.data;
  return (
    <Distribution
      label={`${feature.name} across ${data ? data.count.toLocaleString('en-US') : 'the'} instruments`}
      bins={data ? distributionBins(data) : []}
      markers={
        data
          ? distributionMarkers(
              data,
              threshold === null ? undefined : { label: 'threshold', value: threshold },
            )
          : []
      }
      format={featureFormat(feature)}
      height="sm"
      status={distribution.isError ? 'error' : distribution.isPending ? 'loading' : 'ready'}
      errorMessage="The distribution failed to load."
      onRetry={() => void distribution.refetch()}
    />
  );
}
