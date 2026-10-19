/**
 * The Edges section's top page (`/guide/edges`, ADR 0051, docs/ui/guide.md "Edges"): the
 * section's title and purpose, a way to the live Edges page, a search and the server's filters
 * (asset, side, holding), the nine mechanisms as cards (each a link to its page, with how many
 * edges rest on it by status), the edges checked and set aside with the reason on file and the
 * ideas researched but not built, each with its published verdict. The text, the filters and
 * the counts are the server's; the page only narrows the rows it was sent.
 */
import {
  Button,
  DocSection,
  EmptyState,
  ErrorState,
  FilterChips,
  Grid,
  Heading,
  LinkCard,
  SearchInput,
  Skeleton,
  Stack,
  StatusBadge,
  Text,
  type FilterDefinition,
} from '@algotrade/ui';
import { useState } from 'react';

import {
  EdgeRows,
  edgeStatusText,
  edgeStatusTone,
  IdeaRows,
  mechanismPath,
  useGuideEdgeIndex,
  useGuideIndex,
} from '@/entities/guide';
import { GuideHelp, termHelp } from '@/features/guide-help';

import { cardMatches, edgeMatches, ideaMatches, type EdgeFilters } from '../model/filter';

/** Ideas listed before "Show all". */
const IDEAS_SHOWN = 12;

export interface GuideEdgesIndexProps {
  /** Opens the live Edges page. */
  onOpenEdgesPage: () => void;
}

export function GuideEdgesIndex({ onOpenEdgesPage }: GuideEdgesIndexProps) {
  const query = useGuideEdgeIndex();
  const guide = useGuideIndex();
  const [filters, setFilters] = useState<EdgeFilters>({ query: '' });
  const [all, setAll] = useState(false);
  if (query.isError) {
    return <ErrorState title="The Edges failed to load." onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the Edges" />;
  const index = query.data;
  if (!index) return <EmptyState bordered title="The Guide has no Edges section." />;
  const section = guide.data?.sections.find((s) => s.id === 'edges');
  const titles = new Map(index.mechanisms.map((m) => [m.id, m.title]));

  const definitions: FilterDefinition[] = (
    [
      ['asset', 'Asset', index.filters.assets],
      ['holding', 'Holding', index.filters.holdings],
      ['side', 'Side', index.filters.sides],
    ] as const
  ).map(([id, label, options]) => ({
    id,
    label,
    options: options.map((o) => ({ value: o.id, label: `${o.text} · ${String(o.count)}` })),
  }));

  const cards = index.mechanisms.filter((m) => cardMatches(m, filters));
  const setAside = index.setAside.filter((s) => edgeMatches(s.edge, filters));
  const ideas = index.notBuilt.filter((i) => ideaMatches(i, filters.query));
  const shownIdeas = all ? ideas : ideas.slice(0, IDEAS_SHOWN);

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

      <Stack gap={2} as="section" aria-label="Find an edge">
        <SearchInput
          aria-label="Search the edges"
          placeholder="Search the edges"
          value={filters.query}
          onValueChange={(next) => {
            setFilters({ ...filters, query: next });
          }}
        />
        <FilterChips
          filters={definitions}
          values={{ asset: filters.asset, holding: filters.holding, side: filters.side }}
          onChange={(id, value) => {
            setFilters({ ...filters, [id]: value });
          }}
          onClear={() => {
            setFilters({ query: filters.query });
          }}
        />
      </Stack>

      <Stack gap={3} as="section" aria-label="Mechanisms">
        <Heading level={2}>Mechanisms</Heading>
        {cards.length === 0 ? (
          <EmptyState bordered title="No mechanism matches these filters." />
        ) : (
          <Grid columns={3} gap={3} collapse="md" as="ul" aria-label="The mechanisms">
            {cards.map((m) => (
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
        )}
      </Stack>

      <DocSection id="set-aside">
        <Stack gap={3} as="section" aria-label={index.setAsideTitle}>
          <Stack direction="row" gap={2} align="center">
            <Heading level={2}>{index.setAsideTitle}</Heading>
            {termHelp('edge_status')}
          </Stack>
          <Text as="p" tone="secondary">
            {index.setAsidePurpose}
          </Text>
          {setAside.length === 0 ? (
            <EmptyState bordered title="No edge set aside matches these filters." />
          ) : (
            <EdgeRows
              aria-label={index.setAsideTitle}
              edges={setAside.map((s) => s.edge)}
              mechanisms={titles}
              why={new Map(setAside.map((s) => [s.edge.id, s.why]))}
            />
          )}
        </Stack>
      </DocSection>

      <DocSection id="not-built">
        <Stack gap={3} as="section" aria-label={index.notBuiltTitle}>
          <Stack direction="row" gap={2} align="center">
            <Heading level={2}>{index.notBuiltTitle}</Heading>
            {termHelp('idea_verdict')}
            {termHelp('idea_feasibility')}
          </Stack>
          <Text as="p" tone="secondary">
            {index.notBuiltPurpose}
          </Text>
          {ideas.length === 0 ? (
            <EmptyState bordered title="No idea matches this search." />
          ) : (
            <IdeaRows aria-label={index.notBuiltTitle} ideas={shownIdeas} mechanisms={titles} />
          )}
          {!all && ideas.length > IDEAS_SHOWN && (
            <Stack direction="row">
              <Button
                onClick={() => {
                  setAll(true);
                }}
              >
                {`Show all ${String(ideas.length)} ideas`}
              </Button>
            </Stack>
          )}
        </Stack>
      </DocSection>
    </Stack>
  );
}
