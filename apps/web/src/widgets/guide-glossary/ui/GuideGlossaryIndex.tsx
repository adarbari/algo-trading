/**
 * The glossary index (`/guide/glossary`): the app's own words A to Z, each a link to its page
 * with its one-sentence definition, under its letter. A letter bar jumps to the group.
 */
import { EmptyState, ErrorState, Heading, Skeleton, Stack, Text, TextLink } from '@algotrade/ui';

import { termPath, useGuideIndex } from '@/entities/guide';

interface Term {
  id: string;
  term: string;
  short: string;
}

/** The terms in A to Z order, grouped under their first letter. */
function byLetter(terms: readonly Term[]): [string, Term[]][] {
  const sorted = [...terms].sort((a, b) => a.term.localeCompare(b.term));
  const groups = new Map<string, Term[]>();
  for (const term of sorted) {
    const letter = term.term.charAt(0).toUpperCase();
    groups.set(letter, [...(groups.get(letter) ?? []), term]);
  }
  return [...groups];
}

export function GuideGlossaryIndex() {
  const index = useGuideIndex();
  if (index.isError) {
    return <ErrorState title="The Guide failed to load." onRetry={() => void index.refetch()} />;
  }
  if (index.isPending) return <Skeleton variant="rect" height="lg" label="Loading the glossary" />;
  const section = index.data?.sections.find((s) => s.id === 'glossary');
  const terms = index.data?.terms ?? [];
  if (terms.length === 0) return <EmptyState bordered title="The glossary has no terms yet." />;
  const groups = byLetter(terms);
  return (
    <Stack gap={4}>
      <Stack gap={1}>
        <Heading level={1} size="3xl">
          {section?.title ?? 'Glossary'}
        </Heading>
        {section && (
          <Text as="p" tone="secondary">
            {section.purpose}
          </Text>
        )}
      </Stack>
      <Stack as="nav" aria-label="Letters" direction="row" gap={3} wrap>
        {groups.map(([letter]) => (
          <TextLink key={letter} href={`#letter-${letter}`} mono>
            {letter}
          </TextLink>
        ))}
      </Stack>
      {groups.map(([letter, entries]) => (
        <Stack key={letter} gap={2} as="section" aria-label={`Terms starting with ${letter}`}>
          <Heading level={2} id={`letter-${letter}`}>
            {letter}
          </Heading>
          {entries.map((t) => (
            <Stack key={t.id} gap={0}>
              <TextLink href={termPath(t.id)}>{t.term}</TextLink>
              <Text size="sm" tone="muted">
                {t.short}
              </Text>
            </Stack>
          ))}
        </Stack>
      ))}
    </Stack>
  );
}
