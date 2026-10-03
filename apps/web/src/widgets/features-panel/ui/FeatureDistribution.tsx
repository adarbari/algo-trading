/**
 * One feature across the universe: a histogram with quartile lines and the focused ticker's
 * value highlighted (numbers), or the most frequent values (labels and categories).
 */
import { BarList, Distribution, Panel } from '@algotrade/ui';

import {
  distributionBins,
  distributionMarkers,
  featureFormat,
  featureTitle,
  isNumericFeature,
  useFeatureDistribution,
  type CatalogueFeature,
} from '@/entities/feature';

export interface FeatureDistributionProps {
  feature: CatalogueFeature;
  symbol: string;
  value: unknown;
}

export function FeatureDistribution({ feature, symbol, value }: FeatureDistributionProps) {
  const distribution = useFeatureDistribution(feature.name);
  const data = distribution.data;
  const title = featureTitle(feature.name);
  const status = distribution.isError ? 'error' : distribution.isPending ? 'loading' : 'ready';
  const counted = data ? (data.count - data.nulls).toLocaleString('en-US') : '';
  return (
    <Panel
      title={`${title} across the universe`}
      description={data ? `${counted} tickers with a value · ${data.session}` : undefined}
    >
      {isNumericFeature(feature) ? (
        <Distribution
          label={`${title} across ${counted} tickers`}
          bins={data ? distributionBins(data) : []}
          markers={
            data
              ? distributionMarkers(
                  data,
                  typeof value === 'number' ? { label: symbol, value } : undefined,
                )
              : []
          }
          format={featureFormat(feature)}
          status={status}
          errorMessage="The distribution failed to load."
          onRetry={() => void distribution.refetch()}
          emptyMessage="No values stored for this session."
        />
      ) : (
        <BarList
          label={`${title}: most frequent values`}
          items={(data?.categories ?? []).map((c) => ({
            id: c.value,
            label: c.value,
            value: c.count,
          }))}
          loading={status === 'loading'}
          {...(status === 'error' ? { error: 'The distribution failed to load.' } : {})}
          emptyMessage="No values stored for this session."
        />
      )}
    </Panel>
  );
}
