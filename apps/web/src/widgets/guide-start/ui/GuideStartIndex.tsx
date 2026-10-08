/**
 * The Start here index (`/guide/start`): the how-to pages in the order to read them, each
 * numbered with its title as a link and its one-line summary.
 */
import { EmptyState, ErrorState, Heading, Skeleton, Stack, Text, TextLink } from '@algotrade/ui';

import { startPath, useGuideIndex } from '@/entities/guide';

export function GuideStartIndex() {
  const index = useGuideIndex();
  if (index.isError) {
    return <ErrorState title="The Guide failed to load." onRetry={() => void index.refetch()} />;
  }
  if (index.isPending) return <Skeleton variant="rect" height="lg" label="Loading Start here" />;
  const section = index.data?.sections.find((s) => s.id === 'start');
  const pages = index.data?.startPages ?? [];
  if (pages.length === 0) return <EmptyState bordered title="Start here has no pages yet." />;
  return (
    <Stack gap={4}>
      <Stack gap={1}>
        <Heading level={1} size="3xl">
          {section?.title ?? 'Start here'}
        </Heading>
        {section && (
          <Text as="p" tone="secondary">
            {section.purpose}
          </Text>
        )}
      </Stack>
      <Stack as="ol" gap={3} aria-label="Start here pages, in reading order">
        {pages.map((page) => (
          <Stack as="li" key={page.id} direction="row" gap={3} align="baseline">
            <Text tone="muted" mono>
              {String(page.order)}
            </Text>
            <Stack gap={0}>
              <TextLink href={startPath(page.id)}>{page.title}</TextLink>
              <Text size="sm" tone="muted">
                {page.summary}
              </Text>
            </Stack>
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
}
