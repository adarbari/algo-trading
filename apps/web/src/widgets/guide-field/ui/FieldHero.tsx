/**
 * The hero of a field's page: its catalogue name, its title and, large, what the number means
 * (the field guide's "how to read it", else the definition), then tags: unit, kind, licence and
 * how many names have a value today.
 */
import { Chip, Heading, Mono, Stack, Surface, Text } from '@algotrade/ui';

import { GuideProse, type GuideProseValue } from '@/entities/guide';
import {
  featureMarks,
  featureTitle,
  unitLabel,
  useFeatureDistribution,
  type CatalogueFeature,
} from '@/entities/feature';

export interface FieldHeroProps {
  feature: CatalogueFeature;
  /** "How to read it" split at the field names it mentions (the server's); plain text without. */
  readsLinked?: GuideProseValue | null | undefined;
}

/** Tags in reading order; each says what it is (colour is never the only signal). */
function tags(feature: CatalogueFeature, valued: number | null): string[] {
  const [low, high] = feature.range ?? [];
  const range =
    typeof low === 'number' && typeof high === 'number'
      ? ` · ${String(low)} to ${String(high)}`
      : '';
  return [
    ...(feature.unit ? [`${unitLabel(feature.unit)}${range}`] : []),
    feature.group ? `${feature.kind} · ${feature.group}` : feature.kind,
    `licence ${feature.licence}`,
    ...featureMarks(feature).filter((mark) => mark !== 'personal licence'),
    ...(valued === null ? [] : [`${valued.toLocaleString('en-US')} names have a value today`]),
  ];
}

export function FieldHero({ feature, readsLinked }: FieldHeroProps) {
  const distribution = useFeatureDistribution(feature.name).data;
  const valued =
    distribution && !distribution.unknown ? distribution.count - distribution.nulls : null;
  return (
    <Surface as="section" radius="lg" padding={6} aria-label="What this field means">
      <Stack gap={4}>
        <Stack gap={1}>
          <Mono size="sm" tone="muted">
            {feature.name}
          </Mono>
          <Heading level={1} size="3xl">
            {featureTitle(feature.name)}
          </Heading>
        </Stack>
        <Text as="p" size="xl">
          {readsLinked ? (
            <GuideProse prose={readsLinked} size="xl" />
          ) : (
            (feature.guide?.reads ?? feature.description)
          )}
        </Text>
        <Stack direction="row" gap={2} wrap>
          {tags(feature, valued).map((tag) => (
            <Chip key={tag} label={tag} />
          ))}
        </Stack>
      </Stack>
    </Surface>
  );
}
