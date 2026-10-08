/**
 * One glossary term's page: the term, its one-sentence definition (the hero), the paragraph
 * behind it with the catalogue names linked, and the terms it sends the reader on to.
 */
import { EmptyState, ErrorState, Heading, Skeleton, Stack, Text, TextLink } from '@algotrade/ui';

import { GuideProse, termPath, useGuideTerm } from '@/entities/guide';

export interface GuideTermProps {
  /** The term's id in the URL. */
  id: string;
}

export function GuideTerm({ id }: GuideTermProps) {
  const query = useGuideTerm(id);
  if (query.isError) {
    return <ErrorState title="The term failed to load." onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the term" />;
  const term = query.data;
  if (!term) {
    return (
      <EmptyState
        bordered
        title="No such term"
        description={`The glossary has no term called ${id}.`}
      />
    );
  }
  return (
    <Stack gap={6}>
      <Stack gap={1}>
        <Text size="sm" tone="muted">
          Glossary
        </Text>
        <Heading level={1} size="3xl">
          {term.entry.term}
        </Heading>
        <Text as="p" size="lg" tone="secondary">
          {term.entry.short}
        </Text>
      </Stack>
      <Text as="p">
        <GuideProse prose={term.body} />
      </Text>
      {term.seeAlso.length > 0 && (
        <Stack gap={2} as="section" aria-label="See also">
          <Heading level={2}>See also</Heading>
          {term.seeAlso.map((t) => (
            <Stack key={t.id} gap={0}>
              <TextLink href={termPath(t.id)}>{t.term}</TextLink>
              <Text size="sm" tone="muted">
                {t.short}
              </Text>
            </Stack>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
