/**
 * The Edges section's top page (`/guide/edges`, ADR 0051, docs/ui/guide.md "Edges"): the
 * section's title and purpose, a way to the live Edges page, every mechanism as a card (each a
 * link to its page, with how many edges rest on it by status, whether or not one is live), and
 * the ideas researched but not built, collapsed until opened. The edges themselves are on their
 * mechanism's page. The text and the counts are the server's.
 */
import {
  Button,
  Disclosure,
  DocSection,
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
import { useState } from 'react';

import {
  edgeStatusText,
  edgeStatusTone,
  IdeaRows,
  mechanismPath,
  useGuideEdgeIndex,
  useGuideIndex,
} from '@/entities/guide';
import { GuideHelp, termHelp } from '@/features/guide-help';

/** Ideas listed before "Show all". */
const IDEAS_SHOWN = 12;

export interface GuideEdgesIndexProps {
  /** Opens the live Edges page. */
  onOpenEdgesPage: () => void;
}

export function GuideEdgesIndex({ onOpenEdgesPage }: GuideEdgesIndexProps) {
  const query = useGuideEdgeIndex();
  const guide = useGuideIndex();
  const [all, setAll] = useState(false);
  if (query.isError) {
    return <ErrorState title="The Edges failed to load." onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the Edges" />;
  const index = query.data;
  if (!index) return <EmptyState bordered title="The Guide has no Edges section." />;
  const section = guide.data?.sections.find((s) => s.id === 'edges');
  const titles = new Map(index.mechanisms.map((m) => [m.id, m.title]));

  const shownIdeas = all ? index.notBuilt : index.notBuilt.slice(0, IDEAS_SHOWN);

  return (
    <Stack gap={6}>
      <Stack gap={3}>
        <Heading level={1} size="3xl">
          {section?.title ?? 'Edges'}
        </Heading>
        {section && (
          <Text as="p" size="xl" tone="secondary">
            {section.purpose}
          </Text>
        )}
        <Stack direction="row" gap={2} align="center" wrap>
          <Text tone="secondary">How each edge is doing right now is on the Edges page.</Text>
          <Button variant="primary" onClick={onOpenEdgesPage}>
            Open the Edges page
          </Button>
          <GuideHelp entry={{ kind: 'start', id: 'read_an_edge_page' }} />
        </Stack>
      </Stack>

      <Stack gap={3} as="section" aria-label="Mechanisms">
        <Heading level={2}>Mechanisms</Heading>
        <Grid columns={3} gap={3} collapse="md" as="ul" aria-label="The mechanisms">
          {index.mechanisms.map((m) => (
            <Stack as="li" key={m.id}>
              <LinkCard
                href={mechanismPath(m.id)}
                kicker={m.question}
                title={m.title}
                description={m.short}
                exampleLabel="e.g."
                example={m.examples}
                footer={
                  <>
                    <StatusBadge>{`${String(m.count)} edges`}</StatusBadge>
                    {m.statuses.map((s) => (
                      <StatusBadge key={s.status} tone={edgeStatusTone(s.status)}>
                        {`${edgeStatusText(s.status)} ${String(s.count)}`}
                      </StatusBadge>
                    ))}
                    {m.ideas > 0 && (
                      <StatusBadge>{`${String(m.ideas)} ideas not built`}</StatusBadge>
                    )}
                  </>
                }
              />
            </Stack>
          ))}
        </Grid>
      </Stack>

      <DocSection id="not-built">
        <Disclosure label={index.notBuiltTitle} count={String(index.notBuilt.length)}>
          <Stack gap={3} as="section" aria-label={index.notBuiltTitle}>
            <Stack direction="row" gap={2} align="center">
              {termHelp('idea_verdict')}
              {termHelp('idea_feasibility')}
            </Stack>
            <Text as="p" tone="secondary">
              {index.notBuiltPurpose}
            </Text>
            <IdeaRows aria-label={index.notBuiltTitle} ideas={shownIdeas} mechanisms={titles} />
            {!all && index.notBuilt.length > IDEAS_SHOWN && (
              <Stack direction="row">
                <Button
                  onClick={() => {
                    setAll(true);
                  }}
                >
                  {`Show all ${String(index.notBuilt.length)} ideas`}
                </Button>
              </Stack>
            )}
          </Stack>
        </Disclosure>
      </DocSection>
    </Stack>
  );
}
