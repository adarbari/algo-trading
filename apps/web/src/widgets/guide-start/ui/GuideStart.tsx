/**
 * One Start here page: its number, title and summary, the sections in reading order (each prose
 * with the catalogue names linked), "Where to look next" (the Guide entries the page links to,
 * each by its kind) and the next page in the order.
 */
import { EmptyState, ErrorState, Heading, Skeleton, Stack, Text, TextLink } from '@algotrade/ui';

import {
  GUIDE_KIND_TITLES,
  GuideProse,
  guideEntryPath,
  startPath,
  useGuideIndex,
  useGuideStartPage,
} from '@/entities/guide';

export interface GuideStartProps {
  /** The page's id in the URL. */
  id: string;
}

export function GuideStart({ id }: GuideStartProps) {
  const query = useGuideStartPage(id);
  const index = useGuideIndex();
  if (query.isError) {
    return <ErrorState title="The page failed to load." onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the page" />;
  const page = query.data;
  if (!page) {
    return (
      <EmptyState
        bordered
        title="No such page"
        description={`Start here has no page called ${id}.`}
      />
    );
  }
  const pages = index.data?.startPages ?? [];
  const next = pages[pages.findIndex((p) => p.id === id) + 1];
  return (
    <Stack gap={6}>
      <Stack gap={1}>
        <Text size="sm" tone="muted">
          {`Start here · step ${String(page.entry.order)}`}
        </Text>
        <Heading level={1} size="3xl">
          {page.entry.title}
        </Heading>
        <Text as="p" size="lg" tone="secondary">
          {page.entry.summary}
        </Text>
      </Stack>
      {page.sections.map((section) => (
        <Stack key={section.title} gap={2} as="section" aria-label={section.title}>
          <Heading level={2}>{section.title}</Heading>
          <Text as="p">
            <GuideProse prose={section.body} />
          </Text>
        </Stack>
      ))}
      {page.links.length > 0 && (
        <Stack gap={2} as="section" aria-label="Where to look next">
          <Heading level={2}>Where to look next</Heading>
          {page.links.map((link) => (
            <Stack key={`${link.kind}:${link.id}`} direction="row" gap={3} align="baseline" wrap>
              <TextLink href={guideEntryPath(link.kind, link.id)} mono={link.kind === 'field'}>
                {link.title}
              </TextLink>
              <Text size="sm" tone="muted">
                {GUIDE_KIND_TITLES[link.kind] ?? link.kind}
              </Text>
            </Stack>
          ))}
        </Stack>
      )}
      {next && (
        <Stack gap={1} as="nav" aria-label="Next page">
          <Text size="sm" tone="muted">
            Next
          </Text>
          <TextLink href={startPath(next.id)}>{`${String(next.order)}. ${next.title}`}</TextLink>
        </Stack>
      )}
    </Stack>
  );
}
