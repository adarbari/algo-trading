/**
 * A screener's Guide page (ADR 0051, docs/ui/guide.md section 3): the header (preset id and
 * version, the summary as the hero, a way to today's hits and to the Builder), what a hit
 * looks like beside what it does not check, the criteria table, the caveats before acting, the
 * situations that fool its fields, the edges it implements, related screeners and the sources
 * (the prose's `[n]` markers link to them). A way up to the section and to its category tops it. The prose is the server's
 * (linked at catalogue names); a preset with no prose written shows its criteria alone.
 */
import {
  Banner,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Grid,
  Heading,
  Mono,
  Skeleton,
  SourceList,
  Stack,
  StatusBadge,
  Surface,
  Text,
  TextLink,
} from '@algotrade/ui';

import {
  edgeGuidePath,
  edgeStatusText,
  edgeStatusTone,
  GUIDE_SCREENERS_PATH,
  GuideProse,
  screenerCategoryPath,
  screenerPath,
  sourceAnchor,
  useGuideScreener,
  useGuideScreenerEdges,
  type GuideProseValue,
} from '@/entities/guide';
import { termHelp } from '@/features/guide-help';

import { criteriaColumns } from '../model/columns';
import { BeforeActing } from './BeforeActing';

export interface GuideScreenerProps {
  /** The preset id in the URL. */
  id: string;
  /** Opens that screener's results. */
  onSeeHits: () => void;
  /** Opens the preset in the Builder. */
  onOpenBuilder: () => void;
}

const COLUMNS = criteriaColumns();

function Block({ title, prose }: { title: string; prose: GuideProseValue }) {
  return (
    <Surface as="section" radius="lg" padding={3} aria-label={title}>
      <Stack gap={2}>
        <Heading level={2}>{title}</Heading>
        <Text as="p" tone="secondary">
          <GuideProse prose={prose} tone="secondary" />
        </Text>
      </Stack>
    </Surface>
  );
}

export function GuideScreener({ id, onSeeHits, onOpenBuilder }: GuideScreenerProps) {
  const query = useGuideScreener(id);
  const edges = useGuideScreenerEdges(id).data ?? [];
  if (query.isError) {
    return <ErrorState title="The screener failed to load." onRetry={() => void query.refetch()} />;
  }
  if (query.isPending) return <Skeleton variant="rect" height="lg" label="Loading the screener" />;
  const screener = query.data;
  if (!screener) {
    return (
      <EmptyState
        bordered
        title="No such screener"
        description={`There is no site screen called ${id}.`}
      />
    );
  }
  const { prose } = screener;
  return (
    <Stack gap={6}>
      <Stack gap={3} as="section" aria-label="Screener">
        <Stack direction="row" gap={2} align="center" wrap>
          <TextLink href={GUIDE_SCREENERS_PATH} size="sm">
            Screeners
          </TextLink>
          {screener.family && screener.familyTitle && (
            <TextLink href={screenerCategoryPath(screener.family)} size="sm">
              {screener.familyTitle}
            </TextLink>
          )}
        </Stack>
        <Mono size="sm" tone="muted">
          {`site preset · ${screener.id}${screener.version === null ? '' : ` v${String(screener.version)}`}${screener.familyTitle ? ` · ${screener.familyTitle}` : ''}`}
        </Mono>
        <Heading level={1} size="3xl">
          {screener.name}
        </Heading>
        {prose ? (
          <Text as="p" size="xl">
            <GuideProse prose={prose.summary} size="xl" />
          </Text>
        ) : (
          <Text as="p" tone="muted">
            No screener prose is written for this screen yet; its criteria are below.
          </Text>
        )}
        <Stack direction="row" gap={2} wrap>
          <Button variant="primary" onClick={onSeeHits}>
            See today’s hits
          </Button>
          <Button onClick={onOpenBuilder}>Open in Builder</Button>
        </Stack>
      </Stack>

      {prose && (
        <Grid columns={2} gap={3} collapse="md" align="start">
          <Block title="What a hit looks like" prose={prose.hit} />
          <Banner tone="warning" title="What it does not check">
            <Text as="p">
              <GuideProse prose={prose.notChecked} />
            </Text>
          </Banner>
        </Grid>
      )}

      <Stack gap={2} as="section" aria-label="The criteria">
        <Heading level={2}>The criteria</Heading>
        <DataTable
          label={`${screener.name} criteria`}
          columns={COLUMNS}
          rows={screener.criteria}
          getRowId={(row) => row.name}
          visibleRows={Math.max(screener.criteria.length, 1)}
          activateOnClick={false}
          emptyMessage="This screen has no criteria."
        />
        {screener.tieBreak && (
          <Text size="sm" tone="muted">
            {`Ranked by ${screener.tieBreak}, ${screener.tieBreakDescending ? 'highest' : 'lowest'} first.`}
          </Text>
        )}
      </Stack>

      {edges.length > 0 && (
        <Stack gap={2} as="section" aria-label="Edges it implements">
          <Stack direction="row" gap={2} align="center">
            <Heading level={2}>Edges it implements</Heading>
            {termHelp('edge_status')}
          </Stack>
          <Stack as="ul" gap={2} aria-label="Edges it implements">
            {edges.map((edge) => (
              <Stack as="li" key={edge.id} gap={1}>
                <Stack direction="row" gap={2} align="center" wrap>
                  <TextLink href={edgeGuidePath(edge.id)}>{edge.name}</TextLink>
                  <StatusBadge tone={edgeStatusTone(edge.status)}>
                    {edgeStatusText(edge.status)}
                  </StatusBadge>
                </Stack>
                <Text as="p" size="sm" tone="secondary">
                  {edge.thesis}
                </Text>
              </Stack>
            ))}
          </Stack>
        </Stack>
      )}

      {prose && <BeforeActing caveats={prose.beforeActing} situations={screener.situations} />}

      {screener.related.length > 0 && (
        <Stack gap={2} as="section" aria-label="Related screeners">
          <Heading level={2}>Related screeners</Heading>
          <Stack gap={1}>
            {screener.related.map((r) => (
              <Text key={r.id} size="sm">
                <TextLink href={screenerPath(r.id)} size="inherit">
                  {r.name}
                </TextLink>
                {`: ${r.reason}`}
              </Text>
            ))}
          </Stack>
        </Stack>
      )}

      {prose && prose.sources.length > 0 && (
        <Stack gap={2} as="section" aria-label="Sources">
          <Heading level={2}>Sources</Heading>
          <SourceList
            aria-label="Sources"
            items={prose.sources.map((source, index) => ({
              id: sourceAnchor(index + 1),
              title: source.title,
              ...(source.url === null ? {} : { url: source.url }),
              why: source.note,
            }))}
          />
        </Stack>
      )}
    </Stack>
  );
}
