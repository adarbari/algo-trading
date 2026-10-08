/**
 * The situation index (`/guide/situations`): every situation (a state of the world that fools
 * several fields at once) as a link to its page with how many fields it fools.
 */
import { EmptyState, ErrorState, Heading, Skeleton, Stack, Text, TextLink } from '@algotrade/ui';

import { situationPath, useGuideIndex } from '@/entities/guide';

export function GuideSituationsIndex() {
  const index = useGuideIndex();
  if (index.isError) {
    return <ErrorState title="The Guide failed to load." onRetry={() => void index.refetch()} />;
  }
  if (index.isPending)
    return <Skeleton variant="rect" height="lg" label="Loading the situations" />;
  const section = index.data?.sections.find((s) => s.id === 'situations');
  const situations = index.data?.situations ?? [];
  if (situations.length === 0) return <EmptyState bordered title="The Guide has no situations." />;
  return (
    <Stack gap={4}>
      <Stack gap={1}>
        <Heading level={1} size="3xl">
          {section?.title ?? 'Situations'}
        </Heading>
        {section && (
          <Text as="p" tone="secondary">
            {section.purpose}
          </Text>
        )}
      </Stack>
      <Stack gap={2} as="section" aria-label="Situations">
        {situations.map((s) => (
          <Stack key={s.slug} direction="row" gap={3} align="baseline" wrap>
            <TextLink href={situationPath(s.slug)}>{s.name}</TextLink>
            <Text size="sm" tone="muted">
              {`fools ${String(s.fields)} ${s.fields === 1 ? 'field' : 'fields'}`}
            </Text>
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
}
