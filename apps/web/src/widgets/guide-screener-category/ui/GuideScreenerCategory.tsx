/**
 * A screener family's Guide page (`/guide/screeners/c/<id>`, ADR 0051, docs/ui/guide.md
 * "Screeners"): a way back to the section, the family's title, its purpose as the hero and its
 * intro, then every screener of the family as a row (its name linking to its page, what it asks
 * in a line, the edges that use it). The text is the server's; nothing is written here.
 */
import {
  EmptyState,
  ErrorState,
  Heading,
  Skeleton,
  Stack,
  StatusBadge,
  Text,
  TextLink,
} from '@algotrade/ui';

import {
  edgeGuidePath,
  edgeStatusText,
  edgeStatusTone,
  GUIDE_SCREENERS_PATH,
  screenerPath,
  useGuideScreenerCategory,
} from '@/entities/guide';

export interface GuideScreenerCategoryProps {
  /** The family id in the URL. */
  id: string;
}

export function GuideScreenerCategory({ id }: GuideScreenerCategoryProps) {
  const query = useGuideScreenerCategory(id);
  if (query.isError) {
    return <ErrorState title="The category failed to load." onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the category" />;
  const category = query.data;
  if (!category) {
    return (
      <EmptyState
        bordered
        title="No such category"
        description={`The Guide has no screener category called ${id}.`}
      />
    );
  }
  return (
    <Stack gap={6}>
      <Stack gap={3} as="section" aria-label="Category">
        <Stack direction="row">
          <TextLink href={GUIDE_SCREENERS_PATH} size="sm">
            Screeners
          </TextLink>
        </Stack>
        <Heading level={1} size="3xl">
          {category.title}
        </Heading>
        <Text as="p" size="xl">
          {category.purpose}
        </Text>
        <Text as="p" tone="secondary">
          {category.intro}
        </Text>
      </Stack>

      <Stack gap={3} as="section" aria-label="The screeners in this category">
        <Heading level={2}>{`The screeners (${String(category.screeners.length)})`}</Heading>
        <Stack as="ul" gap={3} aria-label="Screeners">
          {category.screeners.map((screener) => (
            <Stack as="li" key={screener.id} gap={1}>
              <TextLink href={screenerPath(screener.id)}>{screener.name}</TextLink>
              {screener.line && (
                <Text as="p" size="sm" tone="secondary">
                  {screener.line}
                </Text>
              )}
              {screener.edges.length > 0 && (
                <Stack direction="row" gap={2} align="center" wrap>
                  <Text size="sm" tone="muted">
                    Used by
                  </Text>
                  {screener.edges.map((edge) => (
                    <Stack key={edge.id} direction="row" gap={1} align="center">
                      <TextLink href={edgeGuidePath(edge.id)} size="sm">
                        {edge.name}
                      </TextLink>
                      <StatusBadge tone={edgeStatusTone(edge.status)}>
                        {edgeStatusText(edge.status)}
                      </StatusBadge>
                    </Stack>
                  ))}
                </Stack>
              )}
            </Stack>
          ))}
        </Stack>
      </Stack>
    </Stack>
  );
}
