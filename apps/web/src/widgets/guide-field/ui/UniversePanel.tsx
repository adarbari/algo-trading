/**
 * Across the universe today: the field's spread over every name for the session, with the names
 * that pass the chosen criterion highlighted and a count line ("N names pass ... today"). The
 * counts come from the server (`FeatureDistribution.passing`); a text field shows its most
 * frequent values instead of a histogram.
 */
import { BarList, Distribution, Panel, Select, Stack, Text } from '@algotrade/ui';

import { unknownText } from '@/entities/availability';
import {
  distributionBins,
  distributionMarkers,
  featureFormat,
  featureTitle,
  isNumericFeature,
  ruleText,
  useFeatureDistribution,
  type DetailedFeature,
} from '@/entities/feature';

export interface UniversePanelProps {
  feature: DetailedFeature;
  /** Which of the guide's uses is highlighted (an index into `feature.guide.uses`). */
  useIndex: number;
  onUseChange: (index: number) => void;
}

export function UniversePanel({ feature, useIndex, onUseChange }: UniversePanelProps) {
  const distribution = useFeatureDistribution(feature.name);
  const data = distribution.data;
  const uses = feature.guide?.uses ?? [];
  const use = uses[useIndex];
  const passing = data?.passing[useIndex];
  const title = featureTitle(feature.name);
  const counted = data ? (data.count - data.nulls).toLocaleString('en-US') : '';
  const status = distribution.isError ? 'error' : distribution.isPending ? 'loading' : 'ready';
  const nothing = data === null || data?.unknown != null;
  return (
    <Panel
      title="Across the universe today"
      description={data && !nothing ? `${counted} names with a value · ${data.session}` : undefined}
      actions={
        uses.length > 1 ? (
          <Select
            aria-label="Criterion to highlight"
            size="sm"
            width="auto"
            options={uses.map((u, i) => ({ value: String(i), label: u.intent }))}
            value={String(useIndex)}
            onValueChange={(value) => {
              onUseChange(Number(value));
            }}
          />
        ) : undefined
      }
      state={
        status === 'error'
          ? 'error'
          : status === 'loading'
            ? 'loading'
            : nothing
              ? 'empty'
              : 'ready'
      }
      loadingLabel={`Loading ${title} across the universe`}
      errorMessage="The distribution failed to load."
      onRetry={() => void distribution.refetch()}
      emptyMessage={
        data?.unknown
          ? `Nothing is counted: ${unknownText(data.unknown)}.`
          : 'This field is not stored for the session, so nothing is counted.'
      }
    >
      {data && (
        <Stack gap={2}>
          {isNumericFeature(feature) ? (
            <Distribution
              label={`${title} across ${counted} names`}
              bins={distributionBins(data, use ? passing : undefined)}
              markers={distributionMarkers(data)}
              format={featureFormat(feature)}
              {...(use ? { highlightLabel: `pass “${use.intent}”` } : {})}
              emptyMessage="No values stored for this session."
            />
          ) : (
            <BarList
              label={`${title}: most frequent values`}
              items={data.categories.map((c) => ({ id: c.value, label: c.value, value: c.count }))}
              emptyMessage="No values stored for this session."
            />
          )}
          <Text size="sm" tone="secondary">
            {use && passing
              ? `${passing.count.toLocaleString('en-US')} names pass “${use.intent}” today (${ruleText(use)}).`
              : 'The field guide gives no criterion to count against for this field.'}
          </Text>
        </Stack>
      )}
    </Panel>
  );
}
