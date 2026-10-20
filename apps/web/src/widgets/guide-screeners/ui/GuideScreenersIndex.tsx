/**
 * The Screeners section's lead page (`/guide/screeners`, ADR 0051, docs/ui/guide.md
 * "Screeners"): the section's title and purpose, what a screener is and how it differs from an
 * edge, and a card per family (each a link to its page, with how many screeners it holds). The
 * screeners themselves are on their family's page. The text and the counts are the server's.
 */
import {
  EmptyState,
  ErrorState,
  Grid,
  Heading,
  LinkCard,
  Skeleton,
  Stack,
  StatusBadge,
  Text,
} from '@algotrade/ui';

import { screenerCategoryPath, useGuideIndex, useGuideScreenerIndex } from '@/entities/guide';

export function GuideScreenersIndex() {
  const query = useGuideScreenerIndex();
  const guide = useGuideIndex();
  if (query.isError) {
    return (
      <ErrorState title="The Screeners failed to load." onRetry={() => void query.refetch()} />
    );
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the screeners" />;
  const index = query.data;
  if (!index || index.categories.length === 0) {
    return <EmptyState bordered title="The Guide has no screeners." />;
  }
  const section = guide.data?.sections.find((s) => s.id === 'screeners');
  return (
    <Stack gap={6}>
      <Stack gap={3}>
        <Heading level={1} size="3xl">
          {section?.title ?? 'Screeners'}
        </Heading>
        {section && (
          <Text as="p" size="xl" tone="secondary">
            {section.purpose}
          </Text>
        )}
        {index.what && (
          <Text as="p" tone="secondary">
            {index.what}
          </Text>
        )}
        {index.versusEdge && (
          <Text as="p" tone="secondary">
            {index.versusEdge}
          </Text>
        )}
      </Stack>

      <Stack gap={3} as="section" aria-label="Categories">
        <Heading level={2}>Categories</Heading>
        <Grid columns={3} gap={3} collapse="md" as="ul" aria-label="The screener categories">
          {index.categories.map((c) => (
            <Stack as="li" key={c.id}>
              <LinkCard
                href={screenerCategoryPath(c.id)}
                title={c.title}
                description={c.purpose}
                footer={<StatusBadge>{`${String(c.count)} screeners`}</StatusBadge>}
              />
            </Stack>
          ))}
        </Grid>
      </Stack>
    </Stack>
  );
}
