/**
 * The Guide's Market regime section (`/guide/regime`): the section's title and purpose, a way to
 * today's readings on the Regime page, the indicators as their plain-language questions (slow
 * moving, then fast moving: the order the cards come in) and the reference market falls, each a
 * link to its page.
 */
import { EmptyState, ErrorState, Heading, Skeleton, Stack, Text, TextLink } from '@algotrade/ui';

import { episodePath, indicatorPath, REGIME_PAGE_PATH, useGuideIndex } from '@/entities/guide';

const PACES = [
  { pace: 'slow', title: 'Slow-moving warning signs', note: 'Credit, jobs and the yield curve' },
  { pace: 'fast', title: 'Fast-moving market signs', note: 'Trend, volatility and breadth' },
] as const;

export function GuideRegimeIndex() {
  const index = useGuideIndex();
  if (index.isError) {
    return <ErrorState title="The Guide failed to load." onRetry={() => void index.refetch()} />;
  }
  if (index.isPending) return <Skeleton variant="rect" height="lg" label="Loading market regime" />;
  const section = index.data?.sections.find((s) => s.id === 'regime');
  const indicators = index.data?.indicators ?? [];
  const episodes = index.data?.episodes ?? [];
  if (indicators.length === 0 && episodes.length === 0) {
    return <EmptyState bordered title="The Guide has no market regime entries." />;
  }
  return (
    <Stack gap={6}>
      <Stack gap={1}>
        <Heading level={1} size="3xl">
          {section?.title ?? 'Market regime'}
        </Heading>
        {section && (
          <Text as="p" tone="secondary">
            {section.purpose}
          </Text>
        )}
        <TextLink href={REGIME_PAGE_PATH} size="sm">
          Today’s readings on the Regime page
        </TextLink>
      </Stack>
      {PACES.map(({ pace, title, note }) => (
        <Stack key={pace} gap={2} as="section" aria-label={title}>
          <Heading level={2}>{title}</Heading>
          <Text size="sm" tone="muted">
            {note}
          </Text>
          <Stack gap={1}>
            {indicators
              .filter((i) => i.pace === pace)
              .map((i) => (
                <TextLink key={i.key} href={indicatorPath(i.key)}>
                  {i.plainName}
                </TextLink>
              ))}
          </Stack>
        </Stack>
      ))}
      <Stack gap={2} as="section" aria-label="Market falls">
        <Heading level={2}>Market falls we compare with</Heading>
        <Stack gap={1}>
          {episodes.map((e) => (
            <TextLink key={e.key} href={episodePath(e.key)}>
              {e.name}
            </TextLink>
          ))}
        </Stack>
      </Stack>
    </Stack>
  );
}
